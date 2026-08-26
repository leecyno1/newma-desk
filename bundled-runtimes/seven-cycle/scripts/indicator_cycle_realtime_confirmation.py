from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

harmonic_state_filter = import_module(
    "seven_cycle_platform.cycles.state_space"
).harmonic_state_filter

try:
    from scripts.indicator_cycle_contribution import (
        CYCLE_PERIODS,
        MINIMUM_OBSERVATIONS,
        _period_text,
        _ridge_fit,
        _safe_r2,
        _select_alpha_with_minimum,
    )
except ModuleNotFoundError:
    from indicator_cycle_contribution import (
        CYCLE_PERIODS,
        MINIMUM_OBSERVATIONS,
        _period_text,
        _ridge_fit,
        _safe_r2,
        _select_alpha_with_minimum,
    )


MINIMUM_ROLLING_ORIGINS = 8
MAXIMUM_ROLLING_ORIGINS = 12
MINIMUM_ROLLING_R2 = 0.0
MINIMUM_DIRECTION_AGREEMENT = 0.60
MINIMUM_CONTRIBUTION_CORRELATION = 0.30
MINIMUM_COEFFICIENT_SIGN_AGREEMENT = 0.60
MINIMUM_STATE_SPECIFICATION_DIRECTION_AGREEMENT = 2.0 / 3.0
MINIMUM_SIGNAL_TO_UNCERTAINTY = 0.50
SPECIFICATION_RELATIVE_WEIGHT_FLOOR = 0.25
SPECIFICATION_RELATIVE_WEIGHT_CEILING = 4.0
MINIMUM_PEER_SHARED_PEERS = 3
PEER_SHARED_POOL_PRIOR = 8.0
PEER_SHARED_MAX_EVIDENCE_WEIGHT = 0.50
MINIMUM_PEER_SHARED_R2_IMPROVEMENT = 0.01
MINIMUM_PEER_SHARED_DIRECTION_IMPROVEMENT = 0.0
MINIMUM_PEER_SHARED_MAE_IMPROVEMENT = 0.0
MINIMUM_PEER_SHARED_PREDICTION_DIRECTION = 0.50
DYNAMIC_FACTOR_POOL_PRIOR = 8.0
DYNAMIC_FACTOR_MAX_EVIDENCE_WEIGHT = 0.35
DYNAMIC_FACTOR_MINIMUM_HISTORY = 24
NEAREST_FACTOR_MAXIMUM_PEERS = 3
NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION = 0.20
NEAREST_FACTOR_PRIMARY_SPECIFICATION = "primary"
NEAREST_FACTOR_SPECIFICATIONS = (
    (
        NEAREST_FACTOR_PRIMARY_SPECIFICATION,
        {
            "maximum_peers": NEAREST_FACTOR_MAXIMUM_PEERS,
            "minimum_absolute_correlation": (
                NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION
            ),
            "span_multiplier": 1.0,
        },
    ),
    (
        "broader_peer_set",
        {
            "maximum_peers": 5,
            "minimum_absolute_correlation": (
                NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION
            ),
            "span_multiplier": 1.0,
        },
    ),
    (
        "longer_correlation_window",
        {
            "maximum_peers": NEAREST_FACTOR_MAXIMUM_PEERS,
            "minimum_absolute_correlation": (
                NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION
            ),
            "span_multiplier": 1.5,
        },
    ),
)
MINIMUM_NEAREST_FACTOR_STABLE_SPECIFICATIONS = len(
    NEAREST_FACTOR_SPECIFICATIONS
)
MINIMUM_ROLLING_TARGET_VARIANCE_RATIO = 0.01
MINIMUM_DYNAMIC_FACTOR_R2_IMPROVEMENT = 0.01
MINIMUM_DYNAMIC_FACTOR_DIRECTION_IMPROVEMENT = 0.0
MINIMUM_DYNAMIC_FACTOR_MAE_IMPROVEMENT = 0.0
CAUSAL_ORTHOGONALIZATION_PRIMARY_SPAN = 60
CAUSAL_ORTHOGONALIZATION_COMPARISON_SPAN = 120
CAUSAL_ORTHOGONALIZATION_MINIMUM_HISTORY = 24
CAUSAL_ORTHOGONALIZATION_RIDGE_SHARE = 0.01
MINIMUM_ORTHOGONAL_R2_IMPROVEMENT = 0.01
MINIMUM_ORTHOGONAL_COMPARISON_R2_IMPROVEMENT = 0.0
MINIMUM_ORTHOGONAL_SPAN_DIRECTION_AGREEMENT = 2.0 / 3.0
MINIMUM_ORTHOGONAL_SPAN_CORRELATION = 0.50
MODEL_COMPARISON_TOLERANCE = 1e-6
STATE_SPACE_SPECIFICATIONS = (
    (
        "responsive",
        {
            "cycle_variance": 0.50,
            "observation_variance": 0.50,
            "half_life_cycles": 1.5,
        },
    ),
    (
        "baseline",
        {
            "cycle_variance": 0.35,
            "observation_variance": 0.65,
            "half_life_cycles": 2.0,
        },
    ),
    (
        "smooth",
        {
            "cycle_variance": 0.20,
            "observation_variance": 0.80,
            "half_life_cycles": 3.0,
        },
    ),
)


def _direction_agreement(left: pd.Series, right: pd.Series) -> float:
    frame = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if frame.empty:
        return float("nan")
    return float((np.sign(frame["left"]) == np.sign(frame["right"])).mean())


def _rolling_correlation(left: pd.Series, right: pd.Series) -> float:
    frame = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if len(frame) < MINIMUM_ROLLING_ORIGINS:
        return float("nan")
    if float(frame["left"].std(ddof=0)) <= 1e-12:
        return float("nan")
    if float(frame["right"].std(ddof=0)) <= 1e-12:
        return float("nan")
    return float(frame["left"].corr(frame["right"]))


def _coefficient_stability(
    values: list[float],
    latest: float,
) -> tuple[float, float, float]:
    coefficients = np.asarray(values, dtype=float)
    coefficients = coefficients[np.isfinite(coefficients)]
    if coefficients.size < MINIMUM_ROLLING_ORIGINS or not np.isfinite(latest):
        return float("nan"), float("nan"), float("nan")
    median = float(np.median(coefficients))
    robust_deviation = float(
        1.4826 * np.median(np.abs(coefficients - median))
    )
    if abs(latest) <= 1e-12:
        sign_agreement = float("nan")
    else:
        sign_agreement = float(
            np.mean(np.sign(coefficients) == np.sign(latest))
        )
    return median, robust_deviation, sign_agreement


def _state_space_ensemble(
    target: pd.Series,
    period: float,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame, pd.DataFrame]:
    (
        level_frame,
        uncertainty_frame,
        innovation_frame,
    ) = _state_space_specification_frames(target, period)
    rolling_error = _rolling_innovation_error(innovation_frame, period)
    weight_frame = _weights_from_rolling_error(rolling_error)
    return _ensemble_from_specification_frames(
        target,
        level_frame,
        uncertainty_frame,
        weight_frame,
    )


def _state_space_specification_frames(
    target: pd.Series,
    period: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    levels: dict[str, pd.Series] = {}
    uncertainties: dict[str, pd.Series] = {}
    innovations: dict[str, pd.Series] = {}
    for specification_id, parameters in STATE_SPACE_SPECIFICATIONS:
        state = harmonic_state_filter(target, period, **parameters)
        levels[specification_id] = state.level
        uncertainties[specification_id] = state.uncertainty
        innovations[specification_id] = state.innovation
    level_frame = pd.concat(levels, axis=1)
    uncertainty_frame = pd.concat(uncertainties, axis=1)
    innovation_frame = pd.concat(innovations, axis=1)
    return level_frame, uncertainty_frame, innovation_frame


def _rolling_innovation_error(
    innovation_frame: pd.DataFrame,
    period: float,
) -> pd.DataFrame:
    weighting_span = max(24, min(120, int(math.ceil(period / 2.0))))
    weighting_minimum = max(12, min(60, int(math.ceil(period / 4.0))))
    past_error = innovation_frame.pow(2).shift(1)
    return past_error.ewm(
        span=weighting_span,
        adjust=False,
        min_periods=weighting_minimum,
    ).mean()


def _weights_from_rolling_error(
    rolling_error: pd.DataFrame,
) -> pd.DataFrame:
    error_values = rolling_error.to_numpy(dtype=float)
    median_error = rolling_error.median(axis=1, skipna=True).to_numpy(dtype=float)
    valid_weights = (
        np.isfinite(error_values).all(axis=1)
        & np.isfinite(median_error)
        & (median_error > 1e-12)
    )
    weight_values = np.full_like(
        error_values,
        1.0 / len(STATE_SPACE_SPECIFICATIONS),
        dtype=float,
    )
    if valid_weights.any():
        relative_weights = (
            median_error[valid_weights, None]
            / np.maximum(error_values[valid_weights], 1e-12)
        )
        relative_weights = np.clip(
            relative_weights,
            SPECIFICATION_RELATIVE_WEIGHT_FLOOR,
            SPECIFICATION_RELATIVE_WEIGHT_CEILING,
        )
        weight_values[valid_weights] = relative_weights / relative_weights.sum(
            axis=1,
            keepdims=True,
        )
    weight_frame = pd.DataFrame(
        weight_values,
        index=rolling_error.index,
        columns=rolling_error.columns,
        dtype=float,
    )
    return weight_frame


def _ensemble_from_specification_frames(
    target: pd.Series,
    level_frame: pd.DataFrame,
    uncertainty_frame: pd.DataFrame,
    weight_frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame, pd.DataFrame]:
    weight_values = weight_frame.to_numpy(dtype=float)
    level_values = level_frame.to_numpy(dtype=float)
    ensemble_levels = np.sum(weight_values * level_values, axis=1)
    specification_deviation = np.sqrt(
        np.sum(
            weight_values * np.square(level_values - ensemble_levels[:, None]),
            axis=1,
        )
    )
    ensemble_level = pd.Series(
        ensemble_levels,
        index=target.index,
        name=target.name,
        dtype=float,
    )
    ensemble_uncertainty = pd.Series(
        np.sqrt(
            np.sum(
                weight_values
                * np.square(uncertainty_frame.to_numpy(dtype=float)),
                axis=1,
            )
        ),
        index=target.index,
        name=target.name,
        dtype=float,
    )
    ensemble_deviation = pd.Series(
        specification_deviation,
        index=target.index,
        name=target.name,
        dtype=float,
    )
    return (
        ensemble_level,
        ensemble_uncertainty,
        ensemble_deviation,
        level_frame,
        weight_frame,
    )


def _direction_agreement_with_reference(
    values: np.ndarray,
    reference: float,
) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0 or not np.isfinite(reference) or abs(reference) <= 1e-12:
        return float("nan")
    return float(np.mean(np.sign(finite) == np.sign(reference)))


def _rolling_origin_positions(
    observations: int,
    minimum_observations: int,
) -> np.ndarray:
    first_origin = max(
        minimum_observations,
        int(math.ceil(observations * 0.70)),
    )
    final_origin = observations - 2
    if final_origin < first_origin:
        return np.array([], dtype=int)
    candidates = np.arange(first_origin, final_origin + 1, dtype=int)
    if len(candidates) <= MAXIMUM_ROLLING_ORIGINS:
        return candidates
    positions = np.linspace(
        first_origin,
        final_origin,
        num=MAXIMUM_ROLLING_ORIGINS,
    )
    return np.unique(np.rint(positions).astype(int))


def build_realtime_indicator_peer_pool_input(
    standardized: pd.Series,
    retrospective: Mapping[str, object],
    *,
    periods: Mapping[str, float] | None = None,
) -> dict[str, object]:
    if retrospective.get("status") != "retrospective_diagnostic":
        return {
            "status": "unavailable",
            "reason": "缺少可比较的回溯频带贡献。",
        }
    period_map = dict(periods or CYCLE_PERIODS)
    eligible = [
        cycle_id
        for cycle_id in retrospective.get("eligibleCycles", [])
        if cycle_id in period_map
    ]
    if not eligible:
        return {
            "status": "unavailable",
            "reason": "没有周期同时满足回溯贡献与实时状态空间要求。",
        }
    target = pd.to_numeric(standardized, errors="coerce").rename("target")
    rolling_errors: dict[str, pd.DataFrame] = {}
    state_components: dict[str, pd.Series] = {}
    for cycle_id in eligible:
        specification_paths, specification_uncertainties, innovation_frame = (
            _state_space_specification_frames(
                target,
                period_map[cycle_id],
            )
        )
        own_error = _rolling_innovation_error(
            innovation_frame,
            period_map[cycle_id],
        )
        rolling_errors[cycle_id] = own_error
        state_components[cycle_id] = _ensemble_from_specification_frames(
            target,
            specification_paths,
            specification_uncertainties,
            _weights_from_rolling_error(own_error),
        )[0].rename(cycle_id)
    return {
        "status": "available",
        "eligibleCycles": eligible,
        "rollingErrors": rolling_errors,
        "stateComponents": state_components,
    }


def _causal_peer_factor(
    own: pd.Series,
    peers: Mapping[str, pd.Series],
    period: float,
) -> tuple[pd.Series, pd.Series]:
    span = max(60, min(180, int(math.ceil(period))))
    aligned_peers: dict[str, pd.Series] = {}
    own_numeric = pd.to_numeric(own, errors="coerce")
    own_past = own_numeric.shift(1)
    own_scale = own_past.pow(2).ewm(
        span=span,
        adjust=False,
        min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
    ).mean().pow(0.5)
    for peer_id, peer in peers.items():
        peer_numeric = pd.to_numeric(peer, errors="coerce").reindex(own.index)
        peer_past = peer_numeric.shift(1)
        peer_scale = peer_past.pow(2).ewm(
            span=span,
            adjust=False,
            min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
        ).mean().pow(0.5)
        covariance = (own_past * peer_past).ewm(
            span=span,
            adjust=False,
            min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
        ).mean()
        orientation = np.sign(covariance).replace(0.0, np.nan)
        aligned_peers[peer_id] = (
            peer_numeric
            * orientation
            * own_scale
            / peer_scale.where(peer_scale > 1e-12)
        )
    if not aligned_peers:
        empty = pd.Series(np.nan, index=own.index, dtype=float)
        return empty, empty.copy()
    frame = pd.concat(aligned_peers, axis=1)
    eligible = frame.notna().sum(axis=1) >= MINIMUM_PEER_SHARED_PEERS
    factor = frame.median(axis=1, skipna=True).where(eligible)
    dispersion = (
        frame.sub(factor, axis=0).pow(2).median(axis=1, skipna=True).pow(0.5)
    ).where(eligible)
    return factor.rename(own.name), dispersion.rename(own.name)


def _causal_nearest_peer_factor(
    own: pd.Series,
    peers: Mapping[str, pd.Series],
    period: float,
    *,
    maximum_peers: int = NEAREST_FACTOR_MAXIMUM_PEERS,
    minimum_absolute_correlation: float = (
        NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION
    ),
    span_multiplier: float = 1.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    span = max(
        60,
        min(240, int(math.ceil(period * span_multiplier))),
    )
    own_numeric = pd.to_numeric(own, errors="coerce")
    own_past = own_numeric.shift(1)
    own_scale = own_past.pow(2).ewm(
        span=span,
        adjust=False,
        min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
    ).mean().pow(0.5)
    aligned_peers: dict[str, pd.Series] = {}
    peer_scores: dict[str, pd.Series] = {}
    for peer_id, peer in peers.items():
        peer_numeric = pd.to_numeric(peer, errors="coerce").reindex(own.index)
        peer_past = peer_numeric.shift(1)
        peer_scale = peer_past.pow(2).ewm(
            span=span,
            adjust=False,
            min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
        ).mean().pow(0.5)
        covariance = (own_past * peer_past).ewm(
            span=span,
            adjust=False,
            min_periods=DYNAMIC_FACTOR_MINIMUM_HISTORY,
        ).mean()
        correlation = covariance / (
            own_scale * peer_scale
        ).where((own_scale > 1e-12) & (peer_scale > 1e-12))
        orientation = np.sign(correlation).replace(0.0, np.nan)
        aligned_peers[peer_id] = (
            peer_numeric
            * orientation
            * own_scale
            / peer_scale.where(peer_scale > 1e-12)
        )
        peer_scores[peer_id] = correlation.abs().clip(upper=1.0)
    if not aligned_peers:
        empty = pd.Series(np.nan, index=own.index, dtype=float)
        return empty, empty.copy(), empty.copy()
    aligned_frame = pd.concat(aligned_peers, axis=1)
    score_frame = pd.concat(peer_scores, axis=1)
    eligible_scores = score_frame.where(
        score_frame >= minimum_absolute_correlation
    )
    score_rank = eligible_scores.rank(
        axis=1,
        method="first",
        ascending=False,
    )
    selected = score_rank <= maximum_peers
    selected_values = aligned_frame.where(selected)
    selected_scores = eligible_scores.where(selected)
    eligible = selected_values.notna().sum(axis=1) >= MINIMUM_PEER_SHARED_PEERS
    normalized_scores = selected_scores.div(
        selected_scores.sum(axis=1).where(lambda values: values > 1e-12),
        axis=0,
    )
    factor = (selected_values * normalized_scores).sum(
        axis=1,
        min_count=MINIMUM_PEER_SHARED_PEERS,
    ).where(eligible)
    dispersion = np.sqrt(
        (
            selected_values.sub(factor, axis=0).pow(2)
            * normalized_scores
        ).sum(axis=1, min_count=MINIMUM_PEER_SHARED_PEERS)
    ).where(eligible)
    selected_count = selected_values.notna().sum(axis=1).where(eligible)
    return (
        factor.rename(own.name),
        dispersion.rename(own.name),
        selected_count.rename(own.name),
    )


def build_peer_shared_error_pools(
    pool_inputs: Mapping[str, Mapping[str, object]],
    track_metadata: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, dict[str, object]]]:
    available = {
        track_id: pool_input
        for track_id, pool_input in pool_inputs.items()
        if pool_input.get("status") == "available"
        and isinstance(pool_input.get("rollingErrors"), Mapping)
    }
    result: dict[str, dict[str, dict[str, object]]] = {}
    for track_id, pool_input in available.items():
        metadata = track_metadata.get(track_id, {})
        category = metadata.get("category")
        group = metadata.get("group")
        track_pools: dict[str, dict[str, object]] = {}
        rolling_errors = pool_input["rollingErrors"]
        if not isinstance(rolling_errors, Mapping):
            continue
        for cycle_id, own_error in rolling_errors.items():
            if not isinstance(own_error, pd.DataFrame):
                continue
            eligible_peers = [
                peer_id
                for peer_id, peer_input in available.items()
                if peer_id != track_id
                and isinstance(peer_input.get("rollingErrors"), Mapping)
                and cycle_id in peer_input["rollingErrors"]
            ]
            peer_candidates = (
                (
                    "category",
                    str(category),
                    [
                        peer_id
                        for peer_id in eligible_peers
                        if track_metadata.get(peer_id, {}).get("category")
                        == category
                    ],
                ),
                (
                    "group",
                    str(group),
                    [
                        peer_id
                        for peer_id in eligible_peers
                        if track_metadata.get(peer_id, {}).get("group") == group
                    ],
                ),
                ("global", "all", eligible_peers),
            )
            selected = next(
                (
                    (family_level, family_key, peer_ids)
                    for family_level, family_key, peer_ids in peer_candidates
                    if len(peer_ids) >= MINIMUM_PEER_SHARED_PEERS
                ),
                None,
            )
            if selected is None:
                continue
            family_level, family_key, peer_ids = selected
            pooled_columns: dict[str, pd.Series] = {}
            for specification_id, _ in STATE_SPACE_SPECIFICATIONS:
                peer_frame = pd.concat(
                    [
                        pool_inputs[peer_id]["rollingErrors"][cycle_id][
                            specification_id
                        ].rename(peer_id)
                        for peer_id in peer_ids
                    ],
                    axis=1,
                )
                pooled_columns[specification_id] = peer_frame.median(
                    axis=1,
                    skipna=True,
                ).where(
                    peer_frame.notna().sum(axis=1)
                    >= MINIMUM_PEER_SHARED_PEERS
                )
            pooled_error = pd.concat(pooled_columns, axis=1).reindex(
                columns=own_error.columns
            )
            own_states = pool_input.get("stateComponents")
            own_state = (
                own_states.get(cycle_id)
                if isinstance(own_states, Mapping)
                else None
            )
            dynamic_factor = None
            dynamic_dispersion = None
            nearest_specifications: dict[
                str,
                tuple[pd.Series, pd.Series, pd.Series],
            ] = {}
            if isinstance(own_state, pd.Series):
                peer_states = {
                    peer_id: pool_inputs[peer_id]["stateComponents"][cycle_id]
                    for peer_id in peer_ids
                    if isinstance(
                        pool_inputs[peer_id].get("stateComponents"),
                        Mapping,
                    )
                    and isinstance(
                        pool_inputs[peer_id]["stateComponents"].get(cycle_id),
                        pd.Series,
                    )
                }
                if len(peer_states) >= MINIMUM_PEER_SHARED_PEERS:
                    dynamic_factor, dynamic_dispersion = _causal_peer_factor(
                        own_state,
                        peer_states,
                        CYCLE_PERIODS.get(str(cycle_id), 60.0),
                    )
                    for specification_id, parameters in (
                        NEAREST_FACTOR_SPECIFICATIONS
                    ):
                        nearest_specifications[specification_id] = (
                            _causal_nearest_peer_factor(
                                own_state,
                                peer_states,
                                CYCLE_PERIODS.get(str(cycle_id), 60.0),
                                maximum_peers=int(
                                    parameters["maximum_peers"]
                                ),
                                minimum_absolute_correlation=float(
                                    parameters[
                                        "minimum_absolute_correlation"
                                    ]
                                ),
                                span_multiplier=float(
                                    parameters["span_multiplier"]
                                ),
                            )
                        )
            evidence_weight = min(
                PEER_SHARED_MAX_EVIDENCE_WEIGHT,
                len(peer_ids) / (len(peer_ids) + PEER_SHARED_POOL_PRIOR),
            )
            nearest_payload: dict[str, object] = {}
            nearest_specification_payload: dict[str, dict[str, object]] = {}
            nearest_parameters = dict(NEAREST_FACTOR_SPECIFICATIONS)
            for specification_id, (
                nearest_factor,
                nearest_dispersion,
                nearest_peer_count,
            ) in nearest_specifications.items():
                parameters = nearest_parameters[specification_id]
                specification_payload = {
                    "factor": nearest_factor,
                    "dispersion": nearest_dispersion,
                    "peerCount": nearest_peer_count,
                    "evidenceWeight": float(
                        min(
                            DYNAMIC_FACTOR_MAX_EVIDENCE_WEIGHT,
                            int(parameters["maximum_peers"])
                            / (
                                int(parameters["maximum_peers"])
                                + DYNAMIC_FACTOR_POOL_PRIOR
                            ),
                        )
                    ),
                }
                nearest_specification_payload[specification_id] = (
                    specification_payload
                )
                if specification_id == NEAREST_FACTOR_PRIMARY_SPECIFICATION:
                    nearest_payload = {
                        "nearestFactor": nearest_factor,
                        "nearestFactorDispersion": nearest_dispersion,
                        "nearestFactorPeerCount": nearest_peer_count,
                        "nearestFactorEvidenceWeight": specification_payload[
                            "evidenceWeight"
                        ],
                    }
            track_pools[str(cycle_id)] = {
                "familyLevel": family_level,
                "familyKey": family_key,
                "peerCount": len(peer_ids),
                "evidenceWeight": float(evidence_weight),
                "rollingError": pooled_error,
                **(
                    {
                        "dynamicFactor": dynamic_factor,
                        "dynamicFactorDispersion": dynamic_dispersion,
                        "dynamicFactorEvidenceWeight": float(
                            min(
                                DYNAMIC_FACTOR_MAX_EVIDENCE_WEIGHT,
                                len(peer_ids)
                                / (len(peer_ids) + DYNAMIC_FACTOR_POOL_PRIOR),
                            )
                        ),
                    }
                    if isinstance(dynamic_factor, pd.Series)
                    and isinstance(dynamic_dispersion, pd.Series)
                    else {}
                ),
                **nearest_payload,
                "nearestFactorSpecifications": nearest_specification_payload,
            }
        if track_pools:
            result[track_id] = track_pools
    return result


def _peer_blended_error(
    own_error: pd.DataFrame,
    peer_evidence: Mapping[str, object],
) -> pd.DataFrame:
    pooled_error = peer_evidence.get("rollingError")
    evidence_weight = float(peer_evidence.get("evidenceWeight", 0.0))
    if not isinstance(pooled_error, pd.DataFrame) or evidence_weight <= 0.0:
        return own_error
    aligned_peer = pooled_error.reindex(
        index=own_error.index,
        columns=own_error.columns,
    )
    blended = own_error.copy()
    comparable = own_error.notna() & aligned_peer.notna()
    return blended.where(
        ~comparable,
        (1.0 - evidence_weight) * own_error
        + evidence_weight * aligned_peer,
    )


def _dynamic_factor_ensemble(
    target: pd.Series,
    specification_paths: pd.DataFrame,
    specification_uncertainties: pd.DataFrame,
    own_weights: pd.DataFrame,
    peer_evidence: Mapping[str, object] | None,
    *,
    factor_key: str = "dynamicFactor",
    dispersion_key: str = "dynamicFactorDispersion",
    evidence_weight_key: str = "dynamicFactorEvidenceWeight",
) -> tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame, pd.DataFrame]:
    if not isinstance(peer_evidence, Mapping):
        return _ensemble_from_specification_frames(
            target,
            specification_paths,
            specification_uncertainties,
            own_weights,
        )
    factor = peer_evidence.get(factor_key)
    dispersion = peer_evidence.get(dispersion_key)
    evidence_weight = float(
        peer_evidence.get(evidence_weight_key, 0.0)
    )
    if (
        not isinstance(factor, pd.Series)
        or not isinstance(dispersion, pd.Series)
        or evidence_weight <= 0.0
    ):
        return _ensemble_from_specification_frames(
            target,
            specification_paths,
            specification_uncertainties,
            own_weights,
        )
    aligned_factor = factor.reindex(specification_paths.index)
    aligned_dispersion = dispersion.reindex(specification_paths.index)
    comparable = aligned_factor.notna()
    blended_paths = specification_paths.copy()
    blended_uncertainties = specification_uncertainties.copy()
    for specification_id in specification_paths.columns:
        blended_paths.loc[comparable, specification_id] = (
            (1.0 - evidence_weight)
            * specification_paths.loc[comparable, specification_id]
            + evidence_weight * aligned_factor.loc[comparable]
        )
        blended_uncertainties.loc[comparable, specification_id] = np.sqrt(
            np.square(1.0 - evidence_weight)
            * np.square(
                specification_uncertainties.loc[comparable, specification_id]
            )
            + np.square(evidence_weight)
            * np.square(aligned_dispersion.loc[comparable])
        )
    return _ensemble_from_specification_frames(
        target,
        blended_paths,
        blended_uncertainties,
        own_weights,
    )


def _causal_orthogonalize_components(
    components: Mapping[str, pd.Series],
    periods: Mapping[str, float],
    *,
    span: int,
    uncertainties: Mapping[str, pd.Series] | None = None,
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    cycle_ids = sorted(
        components,
        key=lambda cycle_id: periods[cycle_id],
        reverse=True,
    )
    frame = pd.concat(
        [pd.to_numeric(components[cycle_id], errors="coerce").rename(cycle_id)
         for cycle_id in cycle_ids],
        axis=1,
    )
    orthogonal = pd.DataFrame(index=frame.index, columns=cycle_ids, dtype=float)
    orthogonal_uncertainty = pd.DataFrame(
        index=frame.index,
        columns=cycle_ids,
        dtype=float,
    )
    uncertainty_frame = (
        pd.concat(
            [
                pd.to_numeric(uncertainties[cycle_id], errors="coerce").rename(
                    cycle_id
                )
                for cycle_id in cycle_ids
            ],
            axis=1,
        ).reindex(frame.index)
        if uncertainties is not None
        else None
    )
    decay = (float(span) - 1.0) / (float(span) + 1.0)
    for cycle_position, cycle_id in enumerate(cycle_ids):
        values = frame[cycle_id].to_numpy(dtype=float)
        own_uncertainty = (
            uncertainty_frame[cycle_id].to_numpy(dtype=float)
            if uncertainty_frame is not None
            else np.zeros(len(frame), dtype=float)
        )
        if cycle_position == 0:
            orthogonal[cycle_id] = values
            orthogonal_uncertainty[cycle_id] = own_uncertainty
            continue
        previous_ids = cycle_ids[:cycle_position]
        previous_values = orthogonal[previous_ids].to_numpy(dtype=float)
        previous_uncertainty = orthogonal_uncertainty[previous_ids].to_numpy(
            dtype=float
        )
        residual = np.full(len(frame), np.nan, dtype=float)
        residual_uncertainty = np.full(len(frame), np.nan, dtype=float)
        covariance = np.zeros((cycle_position, cycle_position), dtype=float)
        cross_moment = np.zeros(cycle_position, dtype=float)
        observations = 0
        for position in range(len(frame)):
            if (
                position > 0
                and np.isfinite(values[position - 1])
                and np.isfinite(previous_values[position - 1]).all()
            ):
                previous = previous_values[position - 1]
                covariance = (
                    decay * covariance
                    + (1.0 - decay) * np.outer(previous, previous)
                )
                cross_moment = (
                    decay * cross_moment
                    + (1.0 - decay) * previous * values[position - 1]
                )
                observations += 1
            if not (
                np.isfinite(values[position])
                and np.isfinite(previous_values[position]).all()
            ):
                continue
            coefficients = np.zeros(cycle_position, dtype=float)
            if observations >= CAUSAL_ORTHOGONALIZATION_MINIMUM_HISTORY:
                ridge = max(
                    1e-6,
                    CAUSAL_ORTHOGONALIZATION_RIDGE_SHARE
                    * float(np.trace(covariance))
                    / cycle_position,
                )
                coefficients = np.linalg.solve(
                    covariance + ridge * np.eye(cycle_position),
                    cross_moment,
                )
            residual[position] = (
                values[position]
                - float(previous_values[position] @ coefficients)
            )
            if uncertainty_frame is not None:
                residual_uncertainty[position] = float(
                    np.sqrt(
                        own_uncertainty[position] ** 2
                        + np.sum(
                            np.square(coefficients)
                            * np.square(previous_uncertainty[position])
                        )
                    )
                )
            else:
                residual_uncertainty[position] = 0.0
        orthogonal[cycle_id] = residual
        orthogonal_uncertainty[cycle_id] = residual_uncertainty
    return (
        {
            cycle_id: orthogonal[cycle_id].rename(cycle_id)
            for cycle_id in components
        },
        {
            cycle_id: orthogonal_uncertainty[cycle_id].rename(cycle_id)
            for cycle_id in components
        },
    )


def _component_collinearity(
    frame: pd.DataFrame,
    cycle_ids: list[str],
    *,
    window: int = 120,
) -> dict[str, float]:
    values = frame[cycle_ids].dropna().iloc[-window:]
    if len(values) < 12 or len(cycle_ids) < 2:
        return {
            "medianAbsoluteCorrelation": float("nan"),
            "maximumAbsoluteCorrelation": float("nan"),
            "conditionNumber": float("nan"),
        }
    correlation = values.corr().to_numpy(dtype=float)
    upper = np.abs(
        correlation[np.triu_indices(len(cycle_ids), k=1)]
    )
    standardized = (values - values.mean()) / values.std(ddof=0).replace(
        0.0,
        1.0,
    )
    return {
        "medianAbsoluteCorrelation": float(np.nanmedian(upper)),
        "maximumAbsoluteCorrelation": float(np.nanmax(upper)),
        "conditionNumber": float(
            np.linalg.cond(standardized.to_numpy(dtype=float))
        ),
    }


def _mean_absolute_error(actual: np.ndarray, predicted: np.ndarray) -> float:
    if len(actual) == 0 or len(predicted) != len(actual):
        return float("nan")
    return float(np.mean(np.abs(actual - predicted)))


def _prediction_direction_agreement(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> float:
    if len(actual) == 0 or len(predicted) != len(actual):
        return float("nan")
    return float(np.mean(np.sign(actual) == np.sign(predicted)))


def _target_variance_diagnostics(
    actual: np.ndarray,
    reference_variance: float,
) -> dict[str, object]:
    target_variance = (
        float(np.var(actual)) if len(actual) > 0 else float("nan")
    )
    target_variance_ratio = (
        target_variance / reference_variance
        if np.isfinite(target_variance)
        and np.isfinite(reference_variance)
        and reference_variance > 1e-12
        else float("nan")
    )
    low_target_variance = (
        not np.isfinite(target_variance_ratio)
        or target_variance_ratio < MINIMUM_ROLLING_TARGET_VARIANCE_RATIO
    )
    return {
        "targetVariance": target_variance,
        "referenceTargetVariance": reference_variance,
        "targetVarianceRatio": target_variance_ratio,
        "lowTargetVarianceWarning": bool(low_target_variance),
    }


def _challenger_improvements(
    standalone: Mapping[str, object],
    challenger: Mapping[str, object],
) -> dict[str, float]:
    return {
        "r2Improvement": float(challenger["r2"])
        - float(standalone["r2"]),
        "maeImprovement": float(standalone["mae"])
        - float(challenger["mae"]),
        "directionImprovement": float(challenger["directionAgreement"])
        - float(standalone["directionAgreement"]),
    }


def _nearest_factor_adoption_reasons(
    diagnostics: Mapping[str, object],
    improvements: Mapping[str, float],
    *,
    eligible_pool: bool,
) -> list[str]:
    reasons: list[str] = []
    if not eligible_pool:
        reasons.append("no_eligible_nearest_factor_pool")
    if bool(diagnostics.get("lowTargetVarianceWarning")):
        reasons.append("nearest_r2_unreliable_low_target_variance")
    if not np.isfinite(float(diagnostics["r2"])) or float(
        diagnostics["r2"]
    ) <= MINIMUM_ROLLING_R2:
        reasons.append("nearest_rolling_r2_not_positive")
    if (
        not np.isfinite(float(improvements["r2Improvement"]))
        or float(improvements["r2Improvement"])
        < MINIMUM_DYNAMIC_FACTOR_R2_IMPROVEMENT
    ):
        reasons.append("insufficient_nearest_r2_improvement")
    if (
        not np.isfinite(float(improvements["directionImprovement"]))
        or float(improvements["directionImprovement"])
        < MINIMUM_DYNAMIC_FACTOR_DIRECTION_IMPROVEMENT
    ):
        reasons.append("nearest_direction_deteriorated")
    if (
        not np.isfinite(float(improvements["maeImprovement"]))
        or float(improvements["maeImprovement"])
        < MINIMUM_DYNAMIC_FACTOR_MAE_IMPROVEMENT
    ):
        reasons.append("nearest_mae_deteriorated")
    return reasons


def _nearest_factor_vintage_splits(
    standalone: Mapping[str, object],
    challenger: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    targets = np.asarray(standalone["targets"], dtype=float)
    standalone_predictions = np.asarray(
        standalone["predictions"],
        dtype=float,
    )
    challenger_predictions = np.asarray(
        challenger["predictions"],
        dtype=float,
    )
    dates = list(standalone["dates"])
    midpoint = len(targets) // 2
    reference_variance = float(
        standalone.get("referenceTargetVariance", float("nan"))
    )
    result: dict[str, dict[str, object]] = {}
    for split_id, split in (
        ("early", slice(0, midpoint)),
        ("late", slice(midpoint, len(targets))),
    ):
        split_targets = targets[split]
        standalone_split = standalone_predictions[split]
        challenger_split = challenger_predictions[split]
        variance = _target_variance_diagnostics(
            split_targets,
            reference_variance,
        )
        result[split_id] = {
            "originCount": int(len(split_targets)),
            "originStart": (
                _period_text(dates[split.start]) if len(split_targets) else None
            ),
            "originEnd": (
                _period_text(dates[split.stop - 1])
                if len(split_targets)
                else None
            ),
            "r2Improvement": _safe_r2(
                split_targets,
                challenger_split,
            )
            - _safe_r2(split_targets, standalone_split),
            "maeImprovement": _mean_absolute_error(
                split_targets,
                standalone_split,
            )
            - _mean_absolute_error(split_targets, challenger_split),
            "directionImprovement": _prediction_direction_agreement(
                split_targets,
                challenger_split,
            )
            - _prediction_direction_agreement(
                split_targets,
                standalone_split,
            ),
            **variance,
        }
    return result


def _rolling_variant_diagnostics(
    frame: pd.DataFrame,
    cycle_ids: list[str],
    origin_positions: np.ndarray,
    minimum_observations: int,
) -> dict[str, object]:
    predictions: list[float] = []
    targets: list[float] = []
    dates: list[object] = []
    contributions = {cycle_id: [] for cycle_id in cycle_ids}
    coefficients = {cycle_id: [] for cycle_id in cycle_ids}
    for position in origin_positions:
        train = frame.iloc[:position]
        origin = frame.iloc[position]
        alpha, _ = _select_alpha_with_minimum(
            train,
            cycle_ids,
            minimum_observations,
        )
        intercept, fitted_coefficients, _, _ = _ridge_fit(
            train[cycle_ids].to_numpy(dtype=float),
            train["target"].to_numpy(dtype=float),
            alpha,
        )
        predictions.append(
            float(
                intercept
                + origin[cycle_ids].to_numpy(dtype=float)
                @ fitted_coefficients
            )
        )
        targets.append(float(origin["target"]))
        dates.append(origin.name)
        for index, cycle_id in enumerate(cycle_ids):
            contribution = float(origin[cycle_id]) * float(
                fitted_coefficients[index]
            )
            contributions[cycle_id].append(contribution)
            coefficients[cycle_id].append(float(fitted_coefficients[index]))
    actual = np.asarray(targets, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    reference_variance = float(frame["target"].var(ddof=0))
    return {
        "predictions": predictions,
        "targets": targets,
        "dates": dates,
        "contributions": contributions,
        "coefficients": coefficients,
        "r2": _safe_r2(actual, predicted),
        "mae": _mean_absolute_error(actual, predicted),
        "directionAgreement": _prediction_direction_agreement(
            actual,
            predicted,
        ),
        **_target_variance_diagnostics(actual, reference_variance),
    }


def _latest_variant_fit(
    frame: pd.DataFrame,
    target: pd.Series,
    components: Mapping[str, pd.Series],
    cycle_ids: list[str],
    minimum_observations: int,
) -> dict[str, object]:
    latest = frame.index[-1]
    latest_train = frame.iloc[:-1]
    alpha, train_selection_r2 = _select_alpha_with_minimum(
        latest_train,
        cycle_ids,
        minimum_observations,
    )
    intercept, coefficients, _, _ = _ridge_fit(
        latest_train[cycle_ids].to_numpy(dtype=float),
        latest_train["target"].to_numpy(dtype=float),
        alpha,
    )
    contribution_paths = {
        cycle_id: components[cycle_id] * float(coefficients[index])
        for index, cycle_id in enumerate(cycle_ids)
    }
    cycle_total = pd.concat(contribution_paths.values(), axis=1).sum(
        axis=1,
        min_count=len(cycle_ids),
    )
    residual = target - intercept - cycle_total
    return {
        "latest": latest,
        "latestTrain": latest_train,
        "alpha": alpha,
        "trainSelectionR2": train_selection_r2,
        "intercept": intercept,
        "coefficients": coefficients,
        "contributionPaths": contribution_paths,
        "cycleTotal": cycle_total,
        "residual": residual,
    }


def build_realtime_indicator_confirmation(
    standardized: pd.Series,
    retrospective: Mapping[str, object],
    *,
    periods: Mapping[str, float] | None = None,
    minimum_observations: int = MINIMUM_OBSERVATIONS,
    peer_shared_errors: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if retrospective.get("status") != "retrospective_diagnostic":
        return {
            "status": "unavailable",
            "reason": "缺少可比较的回溯频带贡献。",
        }
    retrospective_paths = retrospective.get("paths")
    if not isinstance(retrospective_paths, Mapping):
        return {
            "status": "unavailable",
            "reason": "回溯贡献未保留历史路径，无法进行伪实时验证。",
        }

    period_map = dict(periods or CYCLE_PERIODS)
    eligible = [
        cycle_id
        for cycle_id in retrospective.get("eligibleCycles", [])
        if cycle_id in period_map
    ]
    if not eligible:
        return {
            "status": "unavailable",
            "reason": "没有周期同时满足回溯贡献与实时状态空间要求。",
        }

    target = pd.to_numeric(standardized, errors="coerce").rename("target")
    nearest_variant_ids = {
        specification_id: (
            "nearest_factor"
            if specification_id == NEAREST_FACTOR_PRIMARY_SPECIFICATION
            else f"nearest_factor_{specification_id}"
        )
        for specification_id, _ in NEAREST_FACTOR_SPECIFICATIONS
    }
    base_variant_ids = (
        "track_only",
        "peer_shared",
        "dynamic_factor",
        *nearest_variant_ids.values(),
    )
    variant_components: dict[str, dict[str, pd.Series]] = {
        variant_id: {} for variant_id in base_variant_ids
    }
    variant_uncertainty: dict[str, dict[str, pd.Series]] = {
        variant_id: {} for variant_id in base_variant_ids
    }
    variant_specification_deviation: dict[str, dict[str, pd.Series]] = {
        variant_id: {} for variant_id in base_variant_ids
    }
    variant_specification_paths: dict[str, dict[str, pd.DataFrame]] = {
        variant_id: {} for variant_id in base_variant_ids
    }
    variant_specification_weights: dict[str, dict[str, pd.DataFrame]] = {
        variant_id: {} for variant_id in base_variant_ids
    }
    equal_median_components: dict[str, pd.Series] = {}
    peer_pool_metadata: dict[str, Mapping[str, object]] = {}
    for cycle_id in eligible:
        (
            specification_paths,
            specification_uncertainties,
            innovation_frame,
        ) = _state_space_specification_frames(target, period_map[cycle_id])
        own_error = _rolling_innovation_error(
            innovation_frame,
            period_map[cycle_id],
        )
        own_weights = _weights_from_rolling_error(own_error)
        own_ensemble = _ensemble_from_specification_frames(
            target,
            specification_paths,
            specification_uncertainties,
            own_weights,
        )
        peer_evidence = (peer_shared_errors or {}).get(cycle_id)
        if isinstance(peer_evidence, Mapping) and isinstance(
            peer_evidence.get("rollingError"),
            pd.DataFrame,
        ):
            peer_error = _peer_blended_error(own_error, peer_evidence)
            peer_weights = _weights_from_rolling_error(peer_error)
            peer_pool_metadata[cycle_id] = peer_evidence
        else:
            peer_weights = own_weights
        peer_ensemble = _ensemble_from_specification_frames(
            target,
            specification_paths,
            specification_uncertainties,
            peer_weights,
        )
        dynamic_factor_ensemble = _dynamic_factor_ensemble(
            target,
            specification_paths,
            specification_uncertainties,
            own_weights,
            peer_evidence if isinstance(peer_evidence, Mapping) else None,
        )
        nearest_ensembles: dict[
            str,
            tuple[pd.Series, pd.Series, pd.Series, pd.DataFrame, pd.DataFrame],
        ] = {}
        nearest_specification_evidence = (
            peer_evidence.get("nearestFactorSpecifications", {})
            if isinstance(peer_evidence, Mapping)
            else {}
        )
        for specification_id, _ in NEAREST_FACTOR_SPECIFICATIONS:
            specification_evidence = (
                nearest_specification_evidence.get(specification_id)
                if isinstance(nearest_specification_evidence, Mapping)
                else None
            )
            nearest_ensembles[nearest_variant_ids[specification_id]] = (
                _dynamic_factor_ensemble(
                    target,
                    specification_paths,
                    specification_uncertainties,
                    own_weights,
                    (
                        specification_evidence
                        if isinstance(specification_evidence, Mapping)
                        else None
                    ),
                    factor_key="factor",
                    dispersion_key="dispersion",
                    evidence_weight_key="evidenceWeight",
                )
            )
        for variant_id, ensemble in (
            ("track_only", own_ensemble),
            ("peer_shared", peer_ensemble),
            ("dynamic_factor", dynamic_factor_ensemble),
            *nearest_ensembles.items(),
        ):
            level, uncertainty, deviation, paths, weights = ensemble
            variant_components[variant_id][cycle_id] = level.rename(cycle_id)
            variant_uncertainty[variant_id][cycle_id] = uncertainty.rename(
                cycle_id
            )
            variant_specification_deviation[variant_id][cycle_id] = (
                deviation.rename(cycle_id)
            )
            variant_specification_paths[variant_id][cycle_id] = paths
            variant_specification_weights[variant_id][cycle_id] = weights
        equal_median_components[cycle_id] = specification_paths.median(
            axis=1
        ).rename(cycle_id)

    variant_frames = {
        variant_id: pd.concat(
            [target] + [components[cycle_id] for cycle_id in eligible],
            axis=1,
        ).dropna()
        for variant_id, components in variant_components.items()
    }
    equal_median_frame = pd.concat(
        [target] + [equal_median_components[cycle_id] for cycle_id in eligible],
        axis=1,
    ).dropna()
    common_index = equal_median_frame.index
    for variant_frame in variant_frames.values():
        common_index = common_index.intersection(variant_frame.index)
    variant_frames = {
        variant_id: variant_frame.loc[common_index]
        for variant_id, variant_frame in variant_frames.items()
    }
    equal_median_frame = equal_median_frame.loc[common_index]
    warmup = max(
        36,
        int(math.ceil(max(period_map[cycle_id] for cycle_id in eligible))),
    )
    required_observations = (
        warmup + minimum_observations + MINIMUM_ROLLING_ORIGINS + 1
    )
    if len(variant_frames["track_only"]) < required_observations:
        return {
            "status": "unavailable",
            "reason": "剔除状态空间热身期后，滚动训练与验证历史不足。",
            "eligibleCycles": eligible,
            "observations": int(len(variant_frames["track_only"])),
            "requiredObservations": required_observations,
        }
    variant_frames = {
        variant_id: variant_frame.iloc[warmup:]
        for variant_id, variant_frame in variant_frames.items()
    }
    equal_median_frame = equal_median_frame.iloc[warmup:]
    origin_positions = _rolling_origin_positions(
        len(variant_frames["track_only"]),
        minimum_observations,
    )
    if len(origin_positions) < MINIMUM_ROLLING_ORIGINS:
        return {
            "status": "unavailable",
            "reason": "可用历史截点不足，拒绝生成滚动伪实时确认。",
            "eligibleCycles": eligible,
            "originCount": int(len(origin_positions)),
            "requiredOrigins": MINIMUM_ROLLING_ORIGINS,
        }

    retrospective_component_paths = retrospective_paths.get("components", {})
    if not isinstance(retrospective_component_paths, Mapping) or any(
        cycle_id not in retrospective_component_paths for cycle_id in eligible
    ):
        return {
            "status": "unavailable",
            "reason": "回溯贡献路径缺少可比周期。",
            "eligibleCycles": eligible,
        }

    variant_diagnostics = {
        variant_id: _rolling_variant_diagnostics(
            variant_frame,
            eligible,
            origin_positions,
            minimum_observations,
        )
        for variant_id, variant_frame in variant_frames.items()
    }
    equal_median_diagnostics = _rolling_variant_diagnostics(
        equal_median_frame,
        eligible,
        origin_positions,
        minimum_observations,
    )
    standalone_diagnostics = variant_diagnostics["track_only"]
    low_target_variance_warning = bool(
        standalone_diagnostics.get("lowTargetVarianceWarning")
    )
    peer_diagnostics = variant_diagnostics["peer_shared"]
    peer_r2_improvement = float(peer_diagnostics["r2"]) - float(
        standalone_diagnostics["r2"]
    )
    peer_direction_improvement = float(
        peer_diagnostics["directionAgreement"]
    ) - float(standalone_diagnostics["directionAgreement"])
    peer_mae_improvement = float(standalone_diagnostics["mae"]) - float(
        peer_diagnostics["mae"]
    )
    peer_adoption_reasons: list[str] = []
    if not peer_pool_metadata:
        peer_adoption_reasons.append("no_eligible_peer_pool")
    if low_target_variance_warning:
        peer_adoption_reasons.append("peer_r2_unreliable_low_target_variance")
    if not np.isfinite(float(peer_diagnostics["r2"])) or float(
        peer_diagnostics["r2"]
    ) <= MINIMUM_ROLLING_R2:
        peer_adoption_reasons.append("peer_rolling_r2_not_positive")
    if not np.isfinite(peer_r2_improvement) or (
        peer_r2_improvement < MINIMUM_PEER_SHARED_R2_IMPROVEMENT
    ):
        peer_adoption_reasons.append("insufficient_r2_improvement")
    if not np.isfinite(float(peer_diagnostics["directionAgreement"])) or float(
        peer_diagnostics["directionAgreement"]
    ) < MINIMUM_PEER_SHARED_PREDICTION_DIRECTION:
        peer_adoption_reasons.append("peer_prediction_direction_below_floor")
    if not np.isfinite(peer_direction_improvement) or (
        peer_direction_improvement
        < MINIMUM_PEER_SHARED_DIRECTION_IMPROVEMENT
    ):
        peer_adoption_reasons.append("prediction_direction_deteriorated")
    if not np.isfinite(peer_mae_improvement) or (
        peer_mae_improvement < MINIMUM_PEER_SHARED_MAE_IMPROVEMENT
    ):
        peer_adoption_reasons.append("mae_deteriorated")
    peer_shared_adopted = not peer_adoption_reasons
    dynamic_factor_diagnostics = variant_diagnostics["dynamic_factor"]
    dynamic_factor_r2_improvement = float(
        dynamic_factor_diagnostics["r2"]
    ) - float(standalone_diagnostics["r2"])
    dynamic_factor_direction_improvement = float(
        dynamic_factor_diagnostics["directionAgreement"]
    ) - float(standalone_diagnostics["directionAgreement"])
    dynamic_factor_mae_improvement = float(
        standalone_diagnostics["mae"]
    ) - float(dynamic_factor_diagnostics["mae"])
    dynamic_factor_adoption_reasons: list[str] = []
    dynamic_factor_pools = {
        cycle_id: evidence
        for cycle_id, evidence in peer_pool_metadata.items()
        if isinstance(evidence.get("dynamicFactor"), pd.Series)
    }
    if not dynamic_factor_pools:
        dynamic_factor_adoption_reasons.append("no_eligible_dynamic_factor_pool")
    if low_target_variance_warning:
        dynamic_factor_adoption_reasons.append(
            "factor_r2_unreliable_low_target_variance"
        )
    if not np.isfinite(float(dynamic_factor_diagnostics["r2"])) or float(
        dynamic_factor_diagnostics["r2"]
    ) <= MINIMUM_ROLLING_R2:
        dynamic_factor_adoption_reasons.append("factor_rolling_r2_not_positive")
    if (
        not np.isfinite(dynamic_factor_r2_improvement)
        or dynamic_factor_r2_improvement
        < MINIMUM_DYNAMIC_FACTOR_R2_IMPROVEMENT
    ):
        dynamic_factor_adoption_reasons.append("insufficient_factor_r2_improvement")
    if (
        not np.isfinite(dynamic_factor_direction_improvement)
        or dynamic_factor_direction_improvement
        < MINIMUM_DYNAMIC_FACTOR_DIRECTION_IMPROVEMENT
    ):
        dynamic_factor_adoption_reasons.append("factor_direction_deteriorated")
    if (
        not np.isfinite(dynamic_factor_mae_improvement)
        or dynamic_factor_mae_improvement < MINIMUM_DYNAMIC_FACTOR_MAE_IMPROVEMENT
    ):
        dynamic_factor_adoption_reasons.append("factor_mae_deteriorated")
    dynamic_factor_adopted = not dynamic_factor_adoption_reasons
    nearest_factor_specification_results: dict[str, dict[str, object]] = {}
    for specification_id, parameters in NEAREST_FACTOR_SPECIFICATIONS:
        variant_id = nearest_variant_ids[specification_id]
        diagnostics = variant_diagnostics[variant_id]
        improvements = _challenger_improvements(
            standalone_diagnostics,
            diagnostics,
        )
        pools = {
            cycle_id: evidence
            for cycle_id, evidence in peer_pool_metadata.items()
            if isinstance(
                evidence.get("nearestFactorSpecifications"),
                Mapping,
            )
            and isinstance(
                evidence["nearestFactorSpecifications"].get(
                    specification_id
                ),
                Mapping,
            )
            and isinstance(
                evidence["nearestFactorSpecifications"][specification_id].get(
                    "factor"
                ),
                pd.Series,
            )
        }
        adoption_reasons = _nearest_factor_adoption_reasons(
            diagnostics,
            improvements,
            eligible_pool=bool(pools),
        )
        nearest_factor_specification_results[specification_id] = {
            "variantId": variant_id,
            "maximumPeers": int(parameters["maximum_peers"]),
            "minimumAbsoluteCorrelation": float(
                parameters["minimum_absolute_correlation"]
            ),
            "spanMultiplier": float(parameters["span_multiplier"]),
            "eligibleCycles": sorted(pools),
            "rollingReconstructionR2": diagnostics["r2"],
            "rollingMae": diagnostics["mae"],
            "predictionDirectionAgreement": diagnostics[
                "directionAgreement"
            ],
            **improvements,
            "status": "adopted" if not adoption_reasons else "rejected",
            "adoptionReasons": adoption_reasons,
        }
    nearest_factor_diagnostics = variant_diagnostics["nearest_factor"]
    nearest_primary_result = nearest_factor_specification_results[
        NEAREST_FACTOR_PRIMARY_SPECIFICATION
    ]
    nearest_factor_r2_improvement = float(
        nearest_primary_result["r2Improvement"]
    )
    nearest_factor_mae_improvement = float(
        nearest_primary_result["maeImprovement"]
    )
    nearest_factor_direction_improvement = float(
        nearest_primary_result["directionImprovement"]
    )
    nearest_factor_pools = set(nearest_primary_result["eligibleCycles"])
    nearest_factor_specification_adopted_count = sum(
        result["status"] == "adopted"
        for result in nearest_factor_specification_results.values()
    )
    nearest_factor_specification_stable = len(
        {
            result["status"]
            for result in nearest_factor_specification_results.values()
        }
    ) == 1
    nearest_factor_robustly_adopted = (
        nearest_factor_specification_adopted_count
        == MINIMUM_NEAREST_FACTOR_STABLE_SPECIFICATIONS
    )
    nearest_factor_adoption_reasons = list(
        nearest_primary_result["adoptionReasons"]
    )
    if (
        not nearest_factor_adoption_reasons
        and not nearest_factor_robustly_adopted
    ):
        nearest_factor_adoption_reasons.append(
            "nearest_specification_adoption_disagreement"
        )
    nearest_factor_adopted = not nearest_factor_adoption_reasons
    nearest_factor_vintage_splits = _nearest_factor_vintage_splits(
        standalone_diagnostics,
        nearest_factor_diagnostics,
    )
    accepted_base_variants = ["track_only"]
    if peer_shared_adopted:
        accepted_base_variants.append("peer_shared")
    if dynamic_factor_adopted:
        accepted_base_variants.append("dynamic_factor")
    if nearest_factor_adopted:
        accepted_base_variants.append("nearest_factor")
    base_variant = max(
        accepted_base_variants,
        key=lambda variant_id: (
            float(variant_diagnostics[variant_id]["r2"]),
            -float(variant_diagnostics[variant_id]["mae"]),
        ),
    )
    base_diagnostics = variant_diagnostics[base_variant]
    orthogonal_variant_spans = {
        "causal_orthogonal_primary": (
            CAUSAL_ORTHOGONALIZATION_PRIMARY_SPAN
        ),
        "causal_orthogonal_comparison": (
            CAUSAL_ORTHOGONALIZATION_COMPARISON_SPAN
        ),
    }
    for variant_id, span in orthogonal_variant_spans.items():
        orthogonal_components, orthogonal_uncertainty = (
            _causal_orthogonalize_components(
                variant_components[base_variant],
                period_map,
                span=span,
                uncertainties=variant_uncertainty[base_variant],
            )
        )
        variant_components[variant_id] = orthogonal_components
        variant_uncertainty[variant_id] = orthogonal_uncertainty
        variant_specification_paths[variant_id] = {}
        variant_specification_weights[variant_id] = {}
        variant_specification_deviation[variant_id] = {}
        orthogonal_specifications: dict[str, dict[str, pd.Series]] = {}
        for specification_id, _ in STATE_SPACE_SPECIFICATIONS:
            specification_components = {
                cycle_id: variant_specification_paths[base_variant][cycle_id][
                    specification_id
                ].rename(cycle_id)
                for cycle_id in eligible
            }
            orthogonal_specifications[specification_id], _ = (
                _causal_orthogonalize_components(
                    specification_components,
                    period_map,
                    span=span,
                )
            )
        for cycle_id in eligible:
            specification_frame = pd.concat(
                {
                    specification_id: orthogonal_specifications[
                        specification_id
                    ][cycle_id]
                    for specification_id, _ in STATE_SPACE_SPECIFICATIONS
                },
                axis=1,
            )
            weight_frame = variant_specification_weights[base_variant][
                cycle_id
            ]
            level = orthogonal_components[cycle_id]
            deviation = pd.Series(
                np.sqrt(
                    np.sum(
                        weight_frame.to_numpy(dtype=float)
                        * np.square(
                            specification_frame.to_numpy(dtype=float)
                            - level.to_numpy(dtype=float)[:, None]
                        ),
                        axis=1,
                    )
                ),
                index=level.index,
                name=cycle_id,
                dtype=float,
            )
            variant_specification_paths[variant_id][cycle_id] = (
                specification_frame
            )
            variant_specification_weights[variant_id][cycle_id] = weight_frame
            variant_specification_deviation[variant_id][cycle_id] = deviation
        variant_frame = pd.concat(
            [target]
            + [orthogonal_components[cycle_id] for cycle_id in eligible],
            axis=1,
        ).dropna()
        variant_frames[variant_id] = variant_frame.loc[common_index].iloc[
            warmup:
        ]
        variant_diagnostics[variant_id] = _rolling_variant_diagnostics(
            variant_frames[variant_id],
            eligible,
            origin_positions,
            minimum_observations,
        )

    orthogonal_primary_diagnostics = variant_diagnostics[
        "causal_orthogonal_primary"
    ]
    orthogonal_comparison_diagnostics = variant_diagnostics[
        "causal_orthogonal_comparison"
    ]
    orthogonal_primary_r2_improvement = float(
        orthogonal_primary_diagnostics["r2"]
    ) - float(base_diagnostics["r2"])
    orthogonal_primary_mae_improvement = float(base_diagnostics["mae"]) - float(
        orthogonal_primary_diagnostics["mae"]
    )
    orthogonal_primary_direction_improvement = float(
        orthogonal_primary_diagnostics["directionAgreement"]
    ) - float(base_diagnostics["directionAgreement"])
    orthogonal_comparison_r2_improvement = float(
        orthogonal_comparison_diagnostics["r2"]
    ) - float(base_diagnostics["r2"])
    orthogonal_comparison_mae_improvement = float(
        base_diagnostics["mae"]
    ) - float(orthogonal_comparison_diagnostics["mae"])
    orthogonal_comparison_direction_improvement = float(
        orthogonal_comparison_diagnostics["directionAgreement"]
    ) - float(base_diagnostics["directionAgreement"])
    base_collinearity = _component_collinearity(
        variant_frames[base_variant],
        eligible,
    )
    orthogonal_primary_collinearity = _component_collinearity(
        variant_frames["causal_orthogonal_primary"],
        eligible,
    )
    orthogonal_comparison_collinearity = _component_collinearity(
        variant_frames["causal_orthogonal_comparison"],
        eligible,
    )
    orthogonal_adoption_reasons: list[str] = []
    if low_target_variance_warning:
        orthogonal_adoption_reasons.append(
            "orthogonal_r2_unreliable_low_target_variance"
        )
    if not np.isfinite(float(orthogonal_primary_diagnostics["r2"])) or float(
        orthogonal_primary_diagnostics["r2"]
    ) <= MINIMUM_ROLLING_R2:
        orthogonal_adoption_reasons.append("primary_rolling_r2_not_positive")
    if (
        not np.isfinite(orthogonal_primary_r2_improvement)
        or orthogonal_primary_r2_improvement
        < MINIMUM_ORTHOGONAL_R2_IMPROVEMENT
    ):
        orthogonal_adoption_reasons.append("insufficient_primary_r2_improvement")
    if (
        not np.isfinite(orthogonal_primary_mae_improvement)
        or orthogonal_primary_mae_improvement < -MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("primary_mae_deteriorated")
    if (
        not np.isfinite(orthogonal_primary_direction_improvement)
        or orthogonal_primary_direction_improvement
        < -MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("primary_direction_deteriorated")
    if not np.isfinite(float(orthogonal_comparison_diagnostics["r2"])) or float(
        orthogonal_comparison_diagnostics["r2"]
    ) <= MINIMUM_ROLLING_R2:
        orthogonal_adoption_reasons.append("comparison_rolling_r2_not_positive")
    if (
        not np.isfinite(orthogonal_comparison_r2_improvement)
        or orthogonal_comparison_r2_improvement
        < MINIMUM_ORTHOGONAL_COMPARISON_R2_IMPROVEMENT
    ):
        orthogonal_adoption_reasons.append(
            "comparison_r2_did_not_improve"
        )
    if (
        not np.isfinite(orthogonal_comparison_mae_improvement)
        or orthogonal_comparison_mae_improvement
        < -MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("comparison_mae_deteriorated")
    if (
        not np.isfinite(orthogonal_comparison_direction_improvement)
        or orthogonal_comparison_direction_improvement
        < -MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("comparison_direction_deteriorated")
    if not (
        orthogonal_primary_collinearity["maximumAbsoluteCorrelation"]
        < base_collinearity["maximumAbsoluteCorrelation"]
        - MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("maximum_correlation_not_reduced")
    if not (
        orthogonal_primary_collinearity["conditionNumber"]
        < base_collinearity["conditionNumber"] - MODEL_COMPARISON_TOLERANCE
    ):
        orthogonal_adoption_reasons.append("condition_number_not_reduced")
    causal_orthogonal_adopted = not orthogonal_adoption_reasons
    selected_variant = (
        "causal_orthogonal_primary"
        if causal_orthogonal_adopted
        else base_variant
    )
    selected_diagnostics = variant_diagnostics[selected_variant]
    rolling_r2 = float(selected_diagnostics["r2"])
    equal_median_rolling_r2 = float(equal_median_diagnostics["r2"])
    rolling_r2_improvement_vs_equal_median = (
        rolling_r2 - equal_median_rolling_r2
        if np.isfinite(rolling_r2) and np.isfinite(equal_median_rolling_r2)
        else float("nan")
    )

    variant_latest_fits = {
        variant_id: _latest_variant_fit(
            variant_frames[variant_id],
            target,
            variant_components[variant_id],
            eligible,
            minimum_observations,
        )
        for variant_id in variant_frames
    }
    selected_latest_fit = variant_latest_fits[selected_variant]
    latest = selected_latest_fit["latest"]
    latest_train = selected_latest_fit["latestTrain"]
    latest_alpha = selected_latest_fit["alpha"]
    latest_train_selection_r2 = selected_latest_fit["trainSelectionR2"]
    latest_intercept = selected_latest_fit["intercept"]
    latest_coefficients = selected_latest_fit["coefficients"]
    contribution_paths = selected_latest_fit["contributionPaths"]
    cycle_total = selected_latest_fit["cycleTotal"]
    residual = selected_latest_fit["residual"]
    causal_components = variant_components[selected_variant]
    causal_uncertainty = variant_uncertainty[selected_variant]
    causal_specification_deviation = variant_specification_deviation[
        selected_variant
    ]
    causal_specification_paths = variant_specification_paths[selected_variant]
    causal_specification_weights = variant_specification_weights[
        selected_variant
    ]
    origin_dates = selected_diagnostics["dates"]
    origin_contributions = selected_diagnostics["contributions"]
    origin_coefficients = selected_diagnostics["coefficients"]
    origin_retrospective = {cycle_id: [] for cycle_id in eligible}
    origin_specification_agreements = {cycle_id: [] for cycle_id in eligible}
    for cycle_id in eligible:
        retrospective_path = pd.to_numeric(
            retrospective_component_paths[cycle_id],
            errors="coerce",
        )
        for origin_index, origin_date in enumerate(origin_dates):
            origin_retrospective[cycle_id].append(
                float(retrospective_path.reindex([origin_date]).iloc[0])
            )
            contribution = float(origin_contributions[cycle_id][origin_index])
            coefficient = float(origin_coefficients[cycle_id][origin_index])
            specification_contributions = (
                causal_specification_paths[cycle_id]
                .loc[origin_date]
                .to_numpy(dtype=float)
                * coefficient
            )
            origin_specification_agreements[cycle_id].append(
                _direction_agreement_with_reference(
                    specification_contributions,
                    contribution,
                )
            )

    current_components: dict[str, object] = {}
    confirmed_cycles = 0
    for index, cycle_id in enumerate(eligible):
        rolling_contribution = pd.Series(
            origin_contributions[cycle_id],
            index=origin_dates,
            dtype=float,
        )
        rolling_retrospective = pd.Series(
            origin_retrospective[cycle_id],
            index=origin_dates,
            dtype=float,
        )
        orthogonal_primary_rolling_contribution = pd.Series(
            variant_diagnostics["causal_orthogonal_primary"][
                "contributions"
            ][cycle_id],
            index=origin_dates,
            dtype=float,
        )
        orthogonal_comparison_rolling_contribution = pd.Series(
            variant_diagnostics["causal_orthogonal_comparison"][
                "contributions"
            ][cycle_id],
            index=origin_dates,
            dtype=float,
        )
        orthogonal_span_rolling_direction_agreement = _direction_agreement(
            orthogonal_primary_rolling_contribution,
            orthogonal_comparison_rolling_contribution,
        )
        orthogonal_span_rolling_correlation = _rolling_correlation(
            orthogonal_primary_rolling_contribution,
            orthogonal_comparison_rolling_contribution,
        )
        rolling_direction = _direction_agreement(
            rolling_contribution,
            rolling_retrospective,
        )
        rolling_correlation = _rolling_correlation(
            rolling_contribution,
            rolling_retrospective,
        )
        median_absolute_revision = float(
            (rolling_contribution - rolling_retrospective).abs().median()
        )
        latest_coefficient = float(latest_coefficients[index])
        coefficient_median, coefficient_deviation, coefficient_sign_agreement = (
            _coefficient_stability(
                origin_coefficients[cycle_id],
                latest_coefficient,
            )
        )
        point = float(contribution_paths[cycle_id].loc[latest])
        state_uncertainty = abs(latest_coefficient) * float(
            causal_uncertainty[cycle_id].loc[latest]
        )
        coefficient_uncertainty = abs(
            float(causal_components[cycle_id].loc[latest])
        ) * coefficient_deviation
        specification_contributions = (
            causal_specification_paths[cycle_id]
            .loc[latest]
            .to_numpy(dtype=float)
            * latest_coefficient
        )
        state_specification_direction_agreement = (
            _direction_agreement_with_reference(
                specification_contributions,
                point,
            )
        )
        rolling_specification_agreements = np.asarray(
            origin_specification_agreements[cycle_id],
            dtype=float,
        )
        rolling_state_specification_direction_agreement = float(
            np.nanmean(rolling_specification_agreements)
        )
        state_specification_uncertainty = abs(latest_coefficient) * float(
            causal_specification_deviation[cycle_id].loc[latest]
        )
        standalone_point = float(
            variant_latest_fits["track_only"]["contributionPaths"][cycle_id].loc[
                latest
            ]
        )
        peer_shared_point = float(
            variant_latest_fits["peer_shared"]["contributionPaths"][cycle_id].loc[
                latest
            ]
        )
        dynamic_factor_point = float(
            variant_latest_fits["dynamic_factor"]["contributionPaths"][cycle_id]
            .loc[latest]
        )
        nearest_factor_point = float(
            variant_latest_fits["nearest_factor"]["contributionPaths"][cycle_id]
            .loc[latest]
        )
        nearest_specification_points = {
            specification_id: float(
                variant_latest_fits[nearest_variant_ids[specification_id]][
                    "contributionPaths"
                ][cycle_id].loc[latest]
            )
            for specification_id, _ in NEAREST_FACTOR_SPECIFICATIONS
        }
        nearest_factor_specification_uncertainty = (
            float(
                np.sqrt(
                    np.mean(
                        np.square(
                            np.asarray(
                                list(nearest_specification_points.values()),
                                dtype=float,
                            )
                            - nearest_factor_point
                        )
                    )
                )
            )
            if base_variant == "nearest_factor"
            else 0.0
        )
        nearest_factor_specification_direction_agreement = (
            _direction_agreement_with_reference(
                np.asarray(
                    list(nearest_specification_points.values()),
                    dtype=float,
                ),
                nearest_factor_point,
            )
        )
        base_point = float(
            variant_latest_fits[base_variant]["contributionPaths"][cycle_id].loc[
                latest
            ]
        )
        orthogonal_primary_point = float(
            variant_latest_fits["causal_orthogonal_primary"][
                "contributionPaths"
            ][cycle_id].loc[latest]
        )
        orthogonal_comparison_point = float(
            variant_latest_fits["causal_orthogonal_comparison"][
                "contributionPaths"
            ][cycle_id].loc[latest]
        )
        peer_pooling_uncertainty = (
            abs(peer_shared_point - standalone_point)
            if base_variant == "peer_shared"
            else 0.0
        )
        dynamic_factor_uncertainty = (
            abs(dynamic_factor_point - standalone_point)
            if base_variant == "dynamic_factor"
            else 0.0
        )
        nearest_factor_uncertainty = (
            abs(nearest_factor_point - standalone_point)
            if base_variant == "nearest_factor"
            else 0.0
        )
        orthogonalization_uncertainty = (
            abs(orthogonal_primary_point - base_point)
            if causal_orthogonal_adopted
            else 0.0
        )
        orthogonalization_span_uncertainty = (
            abs(orthogonal_primary_point - orthogonal_comparison_point)
            if causal_orthogonal_adopted
            else 0.0
        )
        orthogonal_span_endpoint_direction_agreement = bool(
            np.sign(orthogonal_primary_point)
            == np.sign(orthogonal_comparison_point)
        )
        orthogonal_span_gate = (
            not causal_orthogonal_adopted
            or (
                orthogonal_span_endpoint_direction_agreement
                and np.isfinite(
                    orthogonal_span_rolling_direction_agreement
                )
                and orthogonal_span_rolling_direction_agreement
                >= MINIMUM_ORTHOGONAL_SPAN_DIRECTION_AGREEMENT
                and np.isfinite(orthogonal_span_rolling_correlation)
                and orthogonal_span_rolling_correlation
                >= MINIMUM_ORTHOGONAL_SPAN_CORRELATION
            )
        )
        latest_specification_weights = causal_specification_weights[cycle_id].loc[
            latest
        ]
        state_specification_effective_count = float(
            1.0
            / np.square(latest_specification_weights.to_numpy(dtype=float)).sum()
        )
        state_specification_weight_entropy = float(
            -np.sum(
                latest_specification_weights.to_numpy(dtype=float)
                * np.log(latest_specification_weights.to_numpy(dtype=float))
            )
            / np.log(len(STATE_SPACE_SPECIFICATIONS))
        )
        uncertainty = float(
            np.sqrt(
                state_uncertainty**2
                + coefficient_uncertainty**2
                + state_specification_uncertainty**2
                + peer_pooling_uncertainty**2
                + dynamic_factor_uncertainty**2
                + nearest_factor_uncertainty**2
                + nearest_factor_specification_uncertainty**2
                + orthogonalization_uncertainty**2
                + orthogonalization_span_uncertainty**2
            )
        )
        coefficient_uncertainty_share = (
            coefficient_uncertainty / uncertainty if uncertainty > 1e-12 else 0.0
        )
        state_specification_uncertainty_share = (
            state_specification_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        peer_pooling_uncertainty_share = (
            peer_pooling_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        dynamic_factor_uncertainty_share = (
            dynamic_factor_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        nearest_factor_uncertainty_share = (
            nearest_factor_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        nearest_factor_specification_uncertainty_share = (
            nearest_factor_specification_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        orthogonalization_uncertainty_share = (
            orthogonalization_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        orthogonalization_span_uncertainty_share = (
            orthogonalization_span_uncertainty / uncertainty
            if uncertainty > 1e-12
            else 0.0
        )
        signal_to_uncertainty = (
            abs(point) / uncertainty if uncertainty > 1e-12 else 0.0
        )
        retrospective_path = pd.to_numeric(
            retrospective_component_paths[cycle_id],
            errors="coerce",
        )
        retrospective_point = float(retrospective_path.loc[latest])
        confirmed = (
            len(origin_positions) >= MINIMUM_ROLLING_ORIGINS
            and not low_target_variance_warning
            and np.isfinite(rolling_r2)
            and rolling_r2 > MINIMUM_ROLLING_R2
            and np.isfinite(rolling_direction)
            and rolling_direction >= MINIMUM_DIRECTION_AGREEMENT
            and np.isfinite(rolling_correlation)
            and rolling_correlation >= MINIMUM_CONTRIBUTION_CORRELATION
            and np.isfinite(coefficient_sign_agreement)
            and coefficient_sign_agreement
            >= MINIMUM_COEFFICIENT_SIGN_AGREEMENT
            and np.isfinite(state_specification_direction_agreement)
            and state_specification_direction_agreement
            >= MINIMUM_STATE_SPECIFICATION_DIRECTION_AGREEMENT
            and np.isfinite(rolling_state_specification_direction_agreement)
            and rolling_state_specification_direction_agreement
            >= MINIMUM_STATE_SPECIFICATION_DIRECTION_AGREEMENT
            and signal_to_uncertainty >= MINIMUM_SIGNAL_TO_UNCERTAINTY
            and orthogonal_span_gate
        )
        if confirmed:
            confirmed_cycles += 1
        current_components[cycle_id] = {
            "status": "limited_confirmed" if confirmed else "weak",
            "pointContribution": point,
            "direction": "positive" if point >= 0.0 else "negative",
            "stateWeightModel": (
                "causal_orthogonal"
                if causal_orthogonal_adopted
                else selected_variant
            ),
            "uncertainty": uncertainty,
            "stateUncertainty": state_uncertainty,
            "coefficientUncertainty": coefficient_uncertainty,
            "coefficientUncertaintyShare": coefficient_uncertainty_share,
            "stateSpecificationCount": len(STATE_SPACE_SPECIFICATIONS),
            "stateSpecificationWeights": {
                specification_id: float(latest_specification_weights[specification_id])
                for specification_id, _ in STATE_SPACE_SPECIFICATIONS
            },
            "stateSpecificationEffectiveCount": (
                state_specification_effective_count
            ),
            "stateSpecificationWeightEntropy": (
                state_specification_weight_entropy
            ),
            "stateSpecificationDirectionAgreement": (
                state_specification_direction_agreement
            ),
            "rollingStateSpecificationDirectionAgreement": (
                rolling_state_specification_direction_agreement
            ),
            "stateSpecificationUncertainty": state_specification_uncertainty,
            "stateSpecificationUncertaintyShare": (
                state_specification_uncertainty_share
            ),
            "peerPoolingUncertainty": peer_pooling_uncertainty,
            "peerPoolingUncertaintyShare": peer_pooling_uncertainty_share,
            "dynamicFactorAdopted": dynamic_factor_adopted,
            "dynamicFactorPointContribution": dynamic_factor_point,
            "dynamicFactorEvidenceWeight": (
                peer_pool_metadata[cycle_id].get(
                    "dynamicFactorEvidenceWeight",
                    0.0,
                )
                if cycle_id in peer_pool_metadata
                else 0.0
            ),
            "dynamicFactorUncertainty": dynamic_factor_uncertainty,
            "dynamicFactorUncertaintyShare": (
                dynamic_factor_uncertainty_share
            ),
            "nearestFactorAdopted": nearest_factor_adopted,
            "nearestFactorPointContribution": nearest_factor_point,
            "nearestFactorEvidenceWeight": (
                peer_pool_metadata[cycle_id].get(
                    "nearestFactorEvidenceWeight",
                    0.0,
                )
                if cycle_id in peer_pool_metadata
                else 0.0
            ),
            "nearestFactorPeerCount": (
                float(
                    peer_pool_metadata[cycle_id]["nearestFactorPeerCount"].loc[
                        latest
                    ]
                )
                if cycle_id in peer_pool_metadata
                and isinstance(
                    peer_pool_metadata[cycle_id].get("nearestFactorPeerCount"),
                    pd.Series,
                )
                else 0.0
            ),
            "nearestFactorUncertainty": nearest_factor_uncertainty,
            "nearestFactorUncertaintyShare": nearest_factor_uncertainty_share,
            "nearestFactorSpecificationPoints": nearest_specification_points,
            "nearestFactorSpecificationDirectionAgreement": (
                nearest_factor_specification_direction_agreement
            ),
            "nearestFactorSpecificationUncertainty": (
                nearest_factor_specification_uncertainty
            ),
            "nearestFactorSpecificationUncertaintyShare": (
                nearest_factor_specification_uncertainty_share
            ),
            "causalOrthogonalAdopted": causal_orthogonal_adopted,
            "orthogonalizationOrder": "long_to_short",
            "orthogonalizationPrimarySpan": (
                CAUSAL_ORTHOGONALIZATION_PRIMARY_SPAN
            ),
            "orthogonalizationComparisonSpan": (
                CAUSAL_ORTHOGONALIZATION_COMPARISON_SPAN
            ),
            "basePointContribution": base_point,
            "orthogonalPointContribution": orthogonal_primary_point,
            "orthogonalComparisonPointContribution": (
                orthogonal_comparison_point
            ),
            "orthogonalizationUncertainty": orthogonalization_uncertainty,
            "orthogonalizationUncertaintyShare": (
                orthogonalization_uncertainty_share
            ),
            "orthogonalizationSpanUncertainty": (
                orthogonalization_span_uncertainty
            ),
            "orthogonalizationSpanUncertaintyShare": (
                orthogonalization_span_uncertainty_share
            ),
            "orthogonalSpanEndpointDirectionAgreement": (
                orthogonal_span_endpoint_direction_agreement
            ),
            "orthogonalSpanRollingDirectionAgreement": (
                orthogonal_span_rolling_direction_agreement
            ),
            "orthogonalSpanRollingCorrelation": (
                orthogonal_span_rolling_correlation
            ),
            "standalonePointContribution": standalone_point,
            "peerSharedPointContribution": peer_shared_point,
            "peerSharedEligible": cycle_id in peer_pool_metadata,
            "peerSharedFamilyLevel": (
                peer_pool_metadata[cycle_id].get("familyLevel")
                if cycle_id in peer_pool_metadata
                else None
            ),
            "peerSharedFamilyKey": (
                peer_pool_metadata[cycle_id].get("familyKey")
                if cycle_id in peer_pool_metadata
                else None
            ),
            "peerSharedPeerCount": (
                peer_pool_metadata[cycle_id].get("peerCount")
                if cycle_id in peer_pool_metadata
                else 0
            ),
            "peerSharedEvidenceWeight": (
                peer_pool_metadata[cycle_id].get("evidenceWeight")
                if cycle_id in peer_pool_metadata
                else 0.0
            ),
            "standaloneStateSpecificationWeights": {
                specification_id: float(
                    variant_specification_weights["track_only"][cycle_id]
                    .loc[latest, specification_id]
                )
                for specification_id, _ in STATE_SPACE_SPECIFICATIONS
            },
            "peerSharedStateSpecificationWeights": {
                specification_id: float(
                    variant_specification_weights["peer_shared"][cycle_id]
                    .loc[latest, specification_id]
                )
                for specification_id, _ in STATE_SPACE_SPECIFICATIONS
            },
            "dynamicFactorStateSpecificationWeights": {
                specification_id: float(
                    variant_specification_weights["dynamic_factor"][cycle_id]
                    .loc[latest, specification_id]
                )
                for specification_id, _ in STATE_SPACE_SPECIFICATIONS
            },
            "nearestFactorStateSpecificationWeights": {
                specification_id: float(
                    variant_specification_weights["nearest_factor"][cycle_id]
                    .loc[latest, specification_id]
                )
                for specification_id, _ in STATE_SPACE_SPECIFICATIONS
            },
            "signalToUncertainty": signal_to_uncertainty,
            "latestCoefficient": latest_coefficient,
            "rollingCoefficientMedian": coefficient_median,
            "rollingCoefficientDeviation": coefficient_deviation,
            "coefficientSignAgreement": coefficient_sign_agreement,
            "rollingDirectionAgreement": rolling_direction,
            "rollingContributionCorrelation": rolling_correlation,
            "medianAbsoluteRevision": median_absolute_revision,
            "retrospectivePointContribution": retrospective_point,
            "endpointDirectionAgreement": bool(
                np.sign(point) == np.sign(retrospective_point)
            ),
        }

    indicator_value = float(target.loc[latest])
    cycle_value = float(cycle_total.loc[latest])
    residual_value = float(residual.loc[latest])
    conservation_error = (
        indicator_value - latest_intercept - cycle_value - residual_value
    )
    return {
        "status": "causal_realtime_confirmation",
        "method": (
            "causal_long_to_short_orthogonal_dynamic_harmonic_ensemble_plus_rolling_origin_ridge"
            if causal_orthogonal_adopted
            else (
                "causal_nearest_factor_weighted_damped_harmonic_ensemble_plus_rolling_origin_ridge"
                if base_variant == "nearest_factor"
                else (
                "causal_dynamic_factor_weighted_damped_harmonic_ensemble_plus_rolling_origin_ridge"
                if base_variant == "dynamic_factor"
                else (
                "causal_peer_shared_dynamic_weighted_damped_harmonic_ensemble_plus_rolling_origin_ridge"
                if base_variant == "peer_shared"
                else "causal_track_only_dynamic_weighted_damped_harmonic_ensemble_plus_rolling_origin_ridge"
                )
                )
            )
        ),
        "eligibleCycles": eligible,
        "summary": {
            "confirmedCycles": confirmed_cycles,
            "comparableCycles": len(eligible),
        },
        "training": {
            "originCount": int(len(origin_positions)),
            "originStart": _period_text(origin_dates[0]),
            "originEnd": _period_text(origin_dates[-1]),
            "minimumTrainObservations": int(origin_positions[0]),
            "latestTrainStart": _period_text(latest_train.index.min()),
            "latestTrainEnd": _period_text(latest_train.index.max()),
            "latestTrainObservations": int(len(latest_train)),
            "selectedAlpha": latest_alpha,
            "latestTrainSelectionR2": latest_train_selection_r2,
            "selectedStateWeightModel": (
                "causal_orthogonal"
                if causal_orthogonal_adopted
                else selected_variant
            ),
            "orthogonalBaseStateWeightModel": base_variant,
            "rollingReconstructionR2": rolling_r2,
            "equalMedianRollingReconstructionR2": equal_median_rolling_r2,
            "rollingR2ImprovementVsEqualMedian": (
                rolling_r2_improvement_vs_equal_median
            ),
            "rollingTargetVariance": standalone_diagnostics[
                "targetVariance"
            ],
            "rollingReferenceTargetVariance": standalone_diagnostics[
                "referenceTargetVariance"
            ],
            "rollingTargetVarianceRatio": standalone_diagnostics[
                "targetVarianceRatio"
            ],
            "lowTargetVarianceWarning": low_target_variance_warning,
            "standaloneRollingReconstructionR2": standalone_diagnostics["r2"],
            "standaloneRollingMae": standalone_diagnostics["mae"],
            "standalonePredictionDirectionAgreement": standalone_diagnostics[
                "directionAgreement"
            ],
            "peerSharedRollingReconstructionR2": peer_diagnostics["r2"],
            "peerSharedRollingMae": peer_diagnostics["mae"],
            "peerSharedPredictionDirectionAgreement": peer_diagnostics[
                "directionAgreement"
            ],
            "peerSharedRollingR2Improvement": peer_r2_improvement,
            "peerSharedMaeImprovement": peer_mae_improvement,
            "peerSharedDirectionImprovement": peer_direction_improvement,
            "peerSharedStatus": (
                "adopted"
                if peer_shared_adopted
                else (
                    "rejected"
                    if peer_pool_metadata
                    else "unavailable"
                )
            ),
            "peerSharedAdoptionReasons": peer_adoption_reasons,
            "peerSharedEligibleCycles": sorted(peer_pool_metadata),
            "dynamicFactorRollingReconstructionR2": (
                dynamic_factor_diagnostics["r2"]
            ),
            "dynamicFactorRollingMae": dynamic_factor_diagnostics["mae"],
            "dynamicFactorPredictionDirectionAgreement": (
                dynamic_factor_diagnostics["directionAgreement"]
            ),
            "dynamicFactorRollingR2Improvement": (
                dynamic_factor_r2_improvement
            ),
            "dynamicFactorMaeImprovement": dynamic_factor_mae_improvement,
            "dynamicFactorDirectionImprovement": (
                dynamic_factor_direction_improvement
            ),
            "dynamicFactorStatus": (
                "adopted"
                if dynamic_factor_adopted
                else (
                    "rejected" if dynamic_factor_pools else "unavailable"
                )
            ),
            "dynamicFactorAdoptionReasons": dynamic_factor_adoption_reasons,
            "dynamicFactorEligibleCycles": sorted(dynamic_factor_pools),
            "nearestFactorRollingReconstructionR2": nearest_factor_diagnostics[
                "r2"
            ],
            "nearestFactorRollingMae": nearest_factor_diagnostics["mae"],
            "nearestFactorPredictionDirectionAgreement": (
                nearest_factor_diagnostics["directionAgreement"]
            ),
            "nearestFactorRollingR2Improvement": nearest_factor_r2_improvement,
            "nearestFactorMaeImprovement": nearest_factor_mae_improvement,
            "nearestFactorDirectionImprovement": (
                nearest_factor_direction_improvement
            ),
            "nearestFactorStatus": (
                "adopted"
                if nearest_factor_adopted
                else (
                    "rejected" if nearest_factor_pools else "unavailable"
                )
            ),
            "nearestFactorAdoptionReasons": nearest_factor_adoption_reasons,
            "nearestFactorEligibleCycles": sorted(nearest_factor_pools),
            "nearestFactorSpecificationStable": (
                nearest_factor_specification_stable
            ),
            "nearestFactorRobustlyAdopted": nearest_factor_robustly_adopted,
            "nearestFactorSpecificationAdoptedCount": (
                nearest_factor_specification_adopted_count
            ),
            "nearestFactorSpecificationCount": len(
                NEAREST_FACTOR_SPECIFICATIONS
            ),
            "nearestFactorSpecifications": (
                nearest_factor_specification_results
            ),
            "nearestFactorVintageSplits": nearest_factor_vintage_splits,
            "causalOrthogonalStatus": (
                "adopted" if causal_orthogonal_adopted else "rejected"
            ),
            "causalOrthogonalAdoptionReasons": orthogonal_adoption_reasons,
            "orthogonalPrimaryRollingReconstructionR2": (
                orthogonal_primary_diagnostics["r2"]
            ),
            "orthogonalPrimaryRollingMae": (
                orthogonal_primary_diagnostics["mae"]
            ),
            "orthogonalPrimaryPredictionDirectionAgreement": (
                orthogonal_primary_diagnostics["directionAgreement"]
            ),
            "orthogonalPrimaryRollingR2Improvement": (
                orthogonal_primary_r2_improvement
            ),
            "orthogonalPrimaryMaeImprovement": (
                orthogonal_primary_mae_improvement
            ),
            "orthogonalPrimaryDirectionImprovement": (
                orthogonal_primary_direction_improvement
            ),
            "orthogonalComparisonRollingReconstructionR2": (
                orthogonal_comparison_diagnostics["r2"]
            ),
            "orthogonalComparisonRollingMae": (
                orthogonal_comparison_diagnostics["mae"]
            ),
            "orthogonalComparisonPredictionDirectionAgreement": (
                orthogonal_comparison_diagnostics["directionAgreement"]
            ),
            "orthogonalComparisonRollingR2Improvement": (
                orthogonal_comparison_r2_improvement
            ),
            "orthogonalComparisonMaeImprovement": (
                orthogonal_comparison_mae_improvement
            ),
            "orthogonalComparisonDirectionImprovement": (
                orthogonal_comparison_direction_improvement
            ),
            "baseComponentCollinearity": base_collinearity,
            "orthogonalPrimaryComponentCollinearity": (
                orthogonal_primary_collinearity
            ),
            "orthogonalComparisonComponentCollinearity": (
                orthogonal_comparison_collinearity
            ),
        },
        "thresholds": {
            "minimumRollingOrigins": MINIMUM_ROLLING_ORIGINS,
            "minimumRollingR2": MINIMUM_ROLLING_R2,
            "minimumDirectionAgreement": MINIMUM_DIRECTION_AGREEMENT,
            "minimumContributionCorrelation": MINIMUM_CONTRIBUTION_CORRELATION,
            "minimumCoefficientSignAgreement": (
                MINIMUM_COEFFICIENT_SIGN_AGREEMENT
            ),
            "minimumStateSpecificationDirectionAgreement": (
                MINIMUM_STATE_SPECIFICATION_DIRECTION_AGREEMENT
            ),
            "minimumSignalToUncertainty": MINIMUM_SIGNAL_TO_UNCERTAINTY,
            "minimumPeerSharedPeers": MINIMUM_PEER_SHARED_PEERS,
            "minimumPeerSharedR2Improvement": (
                MINIMUM_PEER_SHARED_R2_IMPROVEMENT
            ),
            "minimumPeerSharedPredictionDirection": (
                MINIMUM_PEER_SHARED_PREDICTION_DIRECTION
            ),
            "minimumPeerSharedDirectionImprovement": (
                MINIMUM_PEER_SHARED_DIRECTION_IMPROVEMENT
            ),
            "minimumPeerSharedMaeImprovement": (
                MINIMUM_PEER_SHARED_MAE_IMPROVEMENT
            ),
            "minimumDynamicFactorR2Improvement": (
                MINIMUM_DYNAMIC_FACTOR_R2_IMPROVEMENT
            ),
            "minimumDynamicFactorDirectionImprovement": (
                MINIMUM_DYNAMIC_FACTOR_DIRECTION_IMPROVEMENT
            ),
            "minimumDynamicFactorMaeImprovement": (
                MINIMUM_DYNAMIC_FACTOR_MAE_IMPROVEMENT
            ),
            "minimumOrthogonalR2Improvement": (
                MINIMUM_ORTHOGONAL_R2_IMPROVEMENT
            ),
            "minimumOrthogonalComparisonR2Improvement": (
                MINIMUM_ORTHOGONAL_COMPARISON_R2_IMPROVEMENT
            ),
            "minimumOrthogonalSpanDirectionAgreement": (
                MINIMUM_ORTHOGONAL_SPAN_DIRECTION_AGREEMENT
            ),
            "minimumOrthogonalSpanCorrelation": (
                MINIMUM_ORTHOGONAL_SPAN_CORRELATION
            ),
        },
        "stateSpaceSpecifications": {
            specification_id: parameters
            for specification_id, parameters in STATE_SPACE_SPECIFICATIONS
        },
        "stateSpaceWeighting": {
            "method": "capped_inverse_past_innovation_mse",
            "usesCurrentObservation": False,
            "lookbackRule": "EWM span=max(24,min(120,period/2)); minimum=max(12,min(60,period/4))",
            "relativeWeightFloor": SPECIFICATION_RELATIVE_WEIGHT_FLOOR,
            "relativeWeightCeiling": SPECIFICATION_RELATIVE_WEIGHT_CEILING,
            "peerSharedChallenger": {
                "method": "leave_one_track_out_category_then_group_then_global_median_error_pool",
                "minimumPeers": MINIMUM_PEER_SHARED_PEERS,
                "poolPrior": PEER_SHARED_POOL_PRIOR,
                "maximumEvidenceWeight": PEER_SHARED_MAX_EVIDENCE_WEIGHT,
                "selectionUsesRetrospectivePath": False,
            },
            "dynamicFactorChallenger": {
                "method": "leave_one_track_out_peer_median_with_lagged_orientation_and_scale",
                "minimumPeers": MINIMUM_PEER_SHARED_PEERS,
                "poolPrior": DYNAMIC_FACTOR_POOL_PRIOR,
                "maximumEvidenceWeight": DYNAMIC_FACTOR_MAX_EVIDENCE_WEIGHT,
                "orientationUsesCurrentObservation": False,
                "selectionUsesRetrospectivePath": False,
            },
            "nearestFactorChallenger": {
                "method": "leave_one_track_out_top_lagged_correlation_peers",
                "minimumPeers": MINIMUM_PEER_SHARED_PEERS,
                "maximumPeers": NEAREST_FACTOR_MAXIMUM_PEERS,
                "minimumAbsoluteCorrelation": (
                    NEAREST_FACTOR_MINIMUM_ABSOLUTE_CORRELATION
                ),
                "maximumEvidenceWeight": DYNAMIC_FACTOR_MAX_EVIDENCE_WEIGHT,
                "selectionUsesCurrentObservation": False,
                "selectionUsesRetrospectivePath": False,
                "precommittedSpecifications": {
                    specification_id: {
                        "maximumPeers": int(parameters["maximum_peers"]),
                        "minimumAbsoluteCorrelation": float(
                            parameters["minimum_absolute_correlation"]
                        ),
                        "spanMultiplier": float(
                            parameters["span_multiplier"]
                        ),
                        "role": (
                            "model_selection"
                            if specification_id
                            == NEAREST_FACTOR_PRIMARY_SPECIFICATION
                            else "stability_audit_only"
                        ),
                    }
                    for specification_id, parameters in (
                        NEAREST_FACTOR_SPECIFICATIONS
                    )
                },
                "minimumStableSpecifications": (
                    MINIMUM_NEAREST_FACTOR_STABLE_SPECIFICATIONS
                ),
            },
            "causalOrthogonalChallenger": {
                "method": "long_to_short_ewm_gram_schmidt_using_only_lagged_components",
                "primarySpan": CAUSAL_ORTHOGONALIZATION_PRIMARY_SPAN,
                "comparisonSpan": (
                    CAUSAL_ORTHOGONALIZATION_COMPARISON_SPAN
                ),
                "minimumHistory": (
                    CAUSAL_ORTHOGONALIZATION_MINIMUM_HISTORY
                ),
                "ridgeShare": CAUSAL_ORTHOGONALIZATION_RIDGE_SHARE,
                "selectionUsesRetrospectivePath": False,
            },
        },
        "current": {
            "date": _period_text(latest),
            "indicatorValue": indicator_value,
            "baseline": float(latest_intercept),
            "cycleTotal": cycle_value,
            "residual": residual_value,
            "conservationError": float(conservation_error),
            "components": current_components,
        },
        "caveat": (
            "该层只使用当期及过去数据形成状态空间分量；多个历史截点均只用截点前数据重选参数并拟合，"
            "三组全局状态空间参数分别形成因果状态；权重仅依据当时之前的一步创新误差自动更新，"
            "并限制相对权重范围，不使用回溯路径调权，也不按单轨道人工调参。"
            "家族共享层对同类别、同组别或全局可比轨道做留一法误差中位池化，"
            "只作为挑战者；仅当滚动R²至少提升1个百分点、MAE不恶化且方向一致性不下降时才晋级。"
            "动态因子层对同一留一同业池的指标状态做滞后方向和尺度对齐，再按固定上限收缩，"
            "仅在相同滚动截点下R²、MAE和方向同时通过时晋级，模型差异计入总不确定性。"
            "因果正交层按长周期到短周期顺序，仅用前一期及以前的状态估计动态重叠，"
            "并用60期主规格与120期对照规格共同复核；两者均改善且相关性和条件数下降时才晋级。"
            "当前贡献使用最新时点前一期训练；总不确定性同时包含状态滤波误差、"
            "滚动系数漂移、状态空间参数集差异、共享模型晋级时相对单轨道模型的差异，"
            "以及正交模型晋级时相对基础模型和不同正交跨度的差异。"
            "与最终双边滤波路径的一致性仅用于修订诊断，"
            "不是预测准确率或经济因果归因。"
        ),
    }
