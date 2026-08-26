"""Causal adaptive trend-cycle state-space ensemble."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd


_RESULT_FIELDS = (
    "trend",
    "trend_slope",
    "level",
    "quadrature",
    "slope",
    "amplitude",
    "angle",
    "uncertainty",
    "period",
    "period_low",
    "period_high",
    "phase_agreement",
    "boundary_share",
    "selection_strength",
)


@dataclass(frozen=True, slots=True)
class AdaptiveFilterConfig:
    """One trend-cycle noise specification in the robustness ensemble."""

    damping: float
    cycle_variance_ratio: float
    level_variance_ratio: float
    slope_variance_ratio: float
    observation_variance_ratio: float


DEFAULT_ADAPTIVE_FILTER_CONFIGS = (
    AdaptiveFilterConfig(0.980, 0.010, 0.001, 0.0001, 0.08),
    AdaptiveFilterConfig(0.980, 0.020, 0.002, 0.0002, 0.12),
    AdaptiveFilterConfig(0.980, 0.040, 0.003, 0.0003, 0.20),
    AdaptiveFilterConfig(0.990, 0.010, 0.001, 0.0001, 0.12),
    AdaptiveFilterConfig(0.990, 0.020, 0.002, 0.0002, 0.20),
    AdaptiveFilterConfig(0.995, 0.030, 0.003, 0.0003, 0.25),
)


@dataclass(frozen=True, slots=True)
class AdaptiveHarmonicResult:
    """Aligned causal states and dynamic-period diagnostics."""

    trend: pd.Series
    trend_slope: pd.Series
    level: pd.Series
    quadrature: pd.Series
    slope: pd.Series
    amplitude: pd.Series
    angle: pd.Series
    uncertainty: pd.Series
    period: pd.Series
    period_low: pd.Series
    period_high: pd.Series
    phase_agreement: pd.Series
    boundary_share: pd.Series
    selection_strength: pd.Series
    model_count: int

    def __post_init__(self) -> None:
        reference = self.level
        if not isinstance(reference, pd.Series):
            raise TypeError("level must be a pandas Series")
        copied: dict[str, pd.Series] = {}
        for field_name in _RESULT_FIELDS:
            series = object.__getattribute__(self, field_name)
            if not isinstance(series, pd.Series):
                raise TypeError(f"{field_name} must be a pandas Series")
            if not series.index.equals(reference.index):
                raise ValueError(f"{field_name} index must align with level")
            if series.name != reference.name:
                raise ValueError(f"{field_name} name must match level")
            normalized = series.astype("float64", copy=True)
            normalized.to_numpy(copy=False).setflags(write=False)
            copied[field_name] = normalized
        if isinstance(self.model_count, bool) or not isinstance(
            self.model_count,
            Integral,
        ):
            raise TypeError("model_count must be a positive integer")
        if self.model_count < 1:
            raise ValueError("model_count must be a positive integer")
        for field_name, series in copied.items():
            object.__setattr__(self, field_name, series)
        object.__setattr__(self, "model_count", int(self.model_count))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.Series):
            return value.copy(deep=True)
        return value


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _positive_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _validate_config(config: AdaptiveFilterConfig) -> None:
    if not isinstance(config, AdaptiveFilterConfig):
        raise TypeError("filter_configs must contain AdaptiveFilterConfig values")
    damping = _positive_real(config.damping, "damping")
    if damping > 1.0:
        raise ValueError("damping must be at most one")
    for field_name in (
        "cycle_variance_ratio",
        "level_variance_ratio",
        "slope_variance_ratio",
        "observation_variance_ratio",
    ):
        _positive_real(getattr(config, field_name), field_name)


def _candidate_periods(period_min: float, period_max: float, step: float) -> np.ndarray:
    count = int(np.floor((period_max - period_min) / step)) + 1
    periods = period_min + step * np.arange(count, dtype="float64")
    if period_max - periods[-1] > step * 1e-9:
        periods = np.append(periods, period_max)
    return periods


def _causal_scale(observations: np.ndarray, minimum: int) -> float:
    finite = observations[np.isfinite(observations)]
    initial = finite[: max(12, minimum)]
    if len(initial) < 2:
        return 1.0
    variance = float(np.var(initial, ddof=0))
    return max(variance, 1e-6)


def _filter_candidate(
    observations: np.ndarray,
    *,
    period: float,
    scale: float,
    config: AdaptiveFilterConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    angular_frequency = 2.0 * np.pi / period
    damping = config.damping
    transition = np.array(
        [
            [1.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, damping * np.cos(angular_frequency), damping * np.sin(angular_frequency)],
            [0.0, 0.0, -damping * np.sin(angular_frequency), damping * np.cos(angular_frequency)],
        ],
        dtype="float64",
    )
    observation = np.array([1.0, 0.0, 1.0, 0.0], dtype="float64")
    process_covariance = np.diag(
        [
            scale * config.level_variance_ratio,
            scale * config.slope_variance_ratio,
            scale * config.cycle_variance_ratio,
            scale * config.cycle_variance_ratio,
        ]
    )
    observation_variance = scale * config.observation_variance_ratio
    identity = np.eye(4, dtype="float64")
    initial = observations[np.isfinite(observations)]
    state = np.array(
        [float(initial[0]) if len(initial) else 0.0, 0.0, 0.0, 0.0],
        dtype="float64",
    )
    covariance = identity * scale
    states = np.zeros((len(observations), 4), dtype="float64")
    cycle_variances = np.zeros(len(observations), dtype="float64")
    scores = np.full(len(observations), np.nan, dtype="float64")

    for position, observed in enumerate(observations):
        predicted_state = transition @ state
        predicted_covariance = (
            transition @ covariance @ transition.T + process_covariance
        )
        if np.isfinite(observed):
            innovation = float(observed - observation @ predicted_state)
            innovation_variance = float(
                observation @ predicted_covariance @ observation
                + observation_variance
            )
            gain = predicted_covariance @ observation / innovation_variance
            state = predicted_state + gain * innovation
            update = identity - np.outer(gain, observation)
            covariance = (
                update @ predicted_covariance @ update.T
                + np.outer(gain, gain) * observation_variance
            )
            scores[position] = -0.5 * (
                np.log(2.0 * np.pi * innovation_variance)
                + innovation**2 / innovation_variance
            )
        else:
            state = predicted_state
            covariance = predicted_covariance
        states[position] = state
        cycle_variances[position] = max(float(covariance[2, 2]), 0.0)
    return states, scores, cycle_variances


def _select_period_path(
    scores: np.ndarray,
    periods: np.ndarray,
    *,
    score_window: int,
    min_score_observations: int,
    period_prior: float,
    period_prior_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    selected = np.zeros(scores.shape[0], dtype="int64")
    strength = np.zeros(scores.shape[0], dtype="float64")
    previous = period_prior
    period_width = float(periods[-1] - periods[0])
    prior_index = int(np.argmin(np.abs(periods - period_prior)))
    for position in range(scores.shape[0]):
        start = max(0, position - score_window + 1)
        window = scores[start : position + 1]
        counts = np.isfinite(window).sum(axis=0)
        totals = np.nansum(window, axis=0)
        average = np.full(len(periods), -np.inf, dtype="float64")
        supported = counts >= min_score_observations
        average[supported] = totals[supported] / counts[supported]
        average -= period_prior_weight * (
            (periods - period_prior) / period_width
        ) ** 2
        average -= 0.04 * ((periods - previous) / period_width) ** 2
        finite = np.flatnonzero(np.isfinite(average))
        if not len(finite):
            selected[position] = prior_index
            previous = 0.85 * previous + 0.15 * periods[prior_index]
            continue
        order = finite[np.argsort(average[finite])]
        best = int(order[-1])
        selected[position] = best
        if len(order) >= 2:
            dispersion = float(np.std(average[finite], ddof=0))
            margin = float(average[order[-1]] - average[order[-2]])
            strength[position] = np.clip(
                margin / max(dispersion, 1e-12),
                0.0,
                1.0,
            )
        previous = 0.85 * previous + 0.15 * periods[best]
    return selected, strength


def _series(values: pd.Series, data: np.ndarray) -> pd.Series:
    return pd.Series(data, index=values.index, name=values.name, dtype="float64")


def adaptive_harmonic_state_filter(
    values: pd.Series,
    *,
    period_min: float,
    period_max: float,
    period_step: float = 0.5,
    score_window: int = 80,
    min_score_observations: int = 40,
    period_prior: float | None = None,
    period_prior_weight: float = 0.03,
    filter_configs: tuple[AdaptiveFilterConfig, ...] = DEFAULT_ADAPTIVE_FILTER_CONFIGS,
) -> AdaptiveHarmonicResult:
    """Estimate a causal local trend and time-varying harmonic cycle.

    Candidate periods compete on trailing one-step predictive likelihood. A
    small fixed robustness ensemble exposes period and phase disagreement rather
    than hiding it behind one noise specification.
    """

    if not isinstance(values, pd.Series):
        raise TypeError("values must be a pandas Series")
    period_min = _positive_real(period_min, "period_min")
    period_max = _positive_real(period_max, "period_max")
    if period_min >= period_max:
        raise ValueError("period_min must be less than period_max")
    period_step = _positive_real(period_step, "period_step")
    score_window = _positive_integer(score_window, "score_window")
    min_score_observations = _positive_integer(
        min_score_observations,
        "min_score_observations",
    )
    if min_score_observations > score_window:
        raise ValueError("min_score_observations cannot exceed score_window")
    if period_prior is None:
        period_prior = (period_min + period_max) / 2.0
    else:
        period_prior = _positive_real(period_prior, "period_prior")
    if not period_min <= period_prior <= period_max:
        raise ValueError("period_prior must lie inside the search range")
    period_prior_weight = _finite_real(
        period_prior_weight,
        "period_prior_weight",
    )
    if period_prior_weight < 0.0:
        raise ValueError("period_prior_weight must be non-negative")
    if not isinstance(filter_configs, tuple) or not filter_configs:
        raise TypeError("filter_configs must be a non-empty tuple")
    for config in filter_configs:
        _validate_config(config)

    observations = (
        pd.to_numeric(values, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .to_numpy(dtype="float64")
    )
    periods = _candidate_periods(period_min, period_max, period_step)
    scale = _causal_scale(observations, min_score_observations)
    model_states: list[np.ndarray] = []
    model_uncertainties: list[np.ndarray] = []
    model_periods: list[np.ndarray] = []
    model_strengths: list[np.ndarray] = []

    for config in filter_configs:
        candidate_states: list[np.ndarray] = []
        candidate_scores: list[np.ndarray] = []
        candidate_variances: list[np.ndarray] = []
        for period in periods:
            states, scores, variances = _filter_candidate(
                observations,
                period=float(period),
                scale=scale,
                config=config,
            )
            candidate_states.append(states)
            candidate_scores.append(scores)
            candidate_variances.append(variances)
        states_by_period = np.stack(candidate_states, axis=1)
        scores_by_period = np.stack(candidate_scores, axis=1)
        variances_by_period = np.stack(candidate_variances, axis=1)
        selected, strength = _select_period_path(
            scores_by_period,
            periods,
            score_window=score_window,
            min_score_observations=min_score_observations,
            period_prior=period_prior,
            period_prior_weight=period_prior_weight,
        )
        rows = np.arange(len(observations))
        model_states.append(states_by_period[rows, selected])
        model_uncertainties.append(np.sqrt(variances_by_period[rows, selected]))
        model_periods.append(periods[selected])
        model_strengths.append(strength)

    states = np.stack(model_states, axis=0)
    uncertainties = np.stack(model_uncertainties, axis=0)
    selected_periods = np.stack(model_periods, axis=0)
    strengths = np.stack(model_strengths, axis=0)
    model_levels = states[:, :, 2]
    model_quadratures = states[:, :, 3]
    model_slopes = np.zeros_like(model_levels)
    model_slopes[:, 1:] = np.diff(model_levels, axis=1)
    phase_codes = (
        (model_levels >= 0.0).astype("int64") * 2
        + (model_slopes >= 0.0).astype("int64")
    )
    phase_agreement = np.zeros(len(observations), dtype="float64")
    for position in range(len(observations)):
        counts = np.bincount(phase_codes[:, position], minlength=4)
        phase_agreement[position] = counts.max() / len(filter_configs)

    level = np.median(model_levels, axis=0)
    quadrature = np.median(model_quadratures, axis=0)
    slope = np.median(model_slopes, axis=0)
    between_model_variance = np.var(model_levels, axis=0, ddof=0)
    uncertainty = np.sqrt(
        np.median(uncertainties**2, axis=0) + between_model_variance
    )
    period = np.median(selected_periods, axis=0)
    period_low = np.quantile(selected_periods, 0.25, axis=0)
    period_high = np.quantile(selected_periods, 0.75, axis=0)
    boundary = (
        (selected_periods <= period_min + period_step * 0.5)
        | (selected_periods >= period_max - period_step * 0.5)
    ).mean(axis=0)
    angle = np.mod(np.degrees(np.arctan2(quadrature, level)), 360.0)
    return AdaptiveHarmonicResult(
        trend=_series(values, np.median(states[:, :, 0], axis=0)),
        trend_slope=_series(values, np.median(states[:, :, 1], axis=0)),
        level=_series(values, level),
        quadrature=_series(values, quadrature),
        slope=_series(values, slope),
        amplitude=_series(values, np.hypot(level, quadrature)),
        angle=_series(values, angle),
        uncertainty=_series(values, uncertainty),
        period=_series(values, period),
        period_low=_series(values, period_low),
        period_high=_series(values, period_high),
        phase_agreement=_series(values, phase_agreement),
        boundary_share=_series(values, boundary),
        selection_strength=_series(values, np.median(strengths, axis=0)),
        model_count=len(filter_configs),
    )
