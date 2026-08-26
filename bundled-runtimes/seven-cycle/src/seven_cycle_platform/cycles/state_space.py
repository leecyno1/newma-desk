"""Causal damped-harmonic state-space filtering."""

from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd


_RESULT_FIELD_NAMES = (
    "level",
    "quadrature",
    "slope",
    "acceleration",
    "amplitude",
    "angle",
    "innovation",
    "uncertainty",
    "smoothed_level",
)


@dataclass(frozen=True)
class HarmonicStateResult:
    """Aligned harmonic states exposed through defensive Series copies."""

    level: pd.Series
    quadrature: pd.Series
    slope: pd.Series
    acceleration: pd.Series
    amplitude: pd.Series
    angle: pd.Series
    innovation: pd.Series
    uncertainty: pd.Series
    smoothed_level: pd.Series

    def __post_init__(self) -> None:
        reference = object.__getattribute__(self, "level")
        if not isinstance(reference, pd.Series):
            raise TypeError("level must be a pandas Series")
        if reference.dtype != np.dtype("float64"):
            raise ValueError("result Series dtype must be float64")

        reference_index = reference.index
        reference_index_names = reference_index.names
        reference_name = reference.name
        reference_dtype = reference.dtype
        copied_fields: dict[str, pd.Series] = {}
        for field_name in _RESULT_FIELD_NAMES:
            series = object.__getattribute__(self, field_name)
            if not isinstance(series, pd.Series):
                raise TypeError(f"{field_name} must be a pandas Series")
            if not series.index.equals(reference_index):
                raise ValueError(f"{field_name} index must align with level")
            if series.index.names != reference_index_names:
                raise ValueError(f"{field_name} index names must align with level")
            if series.name != reference_name:
                raise ValueError(f"{field_name} name must match level")
            if series.dtype != reference_dtype:
                raise ValueError(f"{field_name} dtype must match level")

            copied = series.copy(deep=True)
            copied.to_numpy(copy=False).setflags(write=False)
            copied_fields[field_name] = copied

        for field_name, copied in copied_fields.items():
            object.__setattr__(self, field_name, copied)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELD_NAMES and isinstance(value, pd.Series):
            return value.copy(deep=True)
        return value


def _real_number(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a real number")
    return float(value)


def _positive_finite(value: object, name: str) -> float:
    numeric = _real_number(value, name)
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return numeric


def _nonnegative_finite(value: object, name: str) -> float:
    numeric = _real_number(value, name)
    if not np.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative and finite")
    return numeric


def _series(values: pd.Series, data: np.ndarray) -> pd.Series:
    return pd.Series(data, index=values.index, name=values.name, dtype="float64")


def _empty_result(values: pd.Series) -> HarmonicStateResult:
    fields = [
        pd.Series(index=values.index, name=values.name, dtype="float64")
        for _ in range(9)
    ]
    return HarmonicStateResult(*fields)


def harmonic_state_filter(
    values: pd.Series,
    period: float,
    *,
    cycle_variance: float = 0.35,
    observation_variance: float = 0.65,
    half_life_cycles: float = 2.0,
) -> HarmonicStateResult:
    """Filter a damped oscillator and derive analytical one-step derivatives.

    ``smoothed_level`` uses the full sample. Every other result field depends only
    on observations available at or before its timestamp.
    """

    period = _positive_finite(period, "period")
    cycle_variance = _nonnegative_finite(cycle_variance, "cycle_variance")
    observation_variance = _nonnegative_finite(
        observation_variance,
        "observation_variance",
    )
    half_life_cycles = _positive_finite(half_life_cycles, "half_life_cycles")

    observations = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    count = observations.size
    if count == 0:
        return _empty_result(values)

    angular_frequency = 2.0 * np.pi / period
    decay_rate = -np.log(2.0) / (half_life_cycles * period)
    damping = 0.5 ** (1.0 / (half_life_cycles * period))
    transition = damping * np.array(
        [
            [np.cos(angular_frequency), np.sin(angular_frequency)],
            [-np.sin(angular_frequency), np.cos(angular_frequency)],
        ],
        dtype="float64",
    )
    observation = np.array([[1.0, 0.0]], dtype="float64")
    process_variance = cycle_variance * (1.0 - damping**2)
    process_covariance = np.eye(2, dtype="float64") * process_variance
    identity = np.eye(2, dtype="float64")

    predicted_states = np.zeros((count, 2), dtype="float64")
    filtered_states = np.zeros((count, 2), dtype="float64")
    predicted_covariances = np.zeros((count, 2, 2), dtype="float64")
    filtered_covariances = np.zeros((count, 2, 2), dtype="float64")
    innovations = np.full(count, np.nan, dtype="float64")

    state = np.zeros(2, dtype="float64")
    covariance = np.eye(2, dtype="float64") * cycle_variance

    for position, observed_value in enumerate(observations):
        predicted_state = transition @ state
        predicted_covariance = transition @ covariance @ transition.T + process_covariance
        predicted_states[position] = predicted_state
        predicted_covariances[position] = predicted_covariance

        if np.isfinite(observed_value):
            innovation = observed_value - (observation @ predicted_state).item()
            innovations[position] = innovation
            innovation_variance = (
                observation @ predicted_covariance @ observation.T
            ).item()
            innovation_variance += observation_variance
            if innovation_variance > 0.0:
                gain = predicted_covariance @ observation.T / innovation_variance
                state = predicted_state + gain[:, 0] * innovation
                update = identity - gain @ observation
                covariance = (
                    update @ predicted_covariance @ update.T
                    + gain * observation_variance @ gain.T
                )
            else:
                state = predicted_state
                covariance = predicted_covariance
        else:
            state = predicted_state
            covariance = predicted_covariance

        filtered_states[position] = state
        filtered_covariances[position] = covariance

    smoothed_states = filtered_states.copy()
    for position in range(count - 2, -1, -1):
        smoothing_gain = (
            filtered_covariances[position]
            @ transition.T
            @ np.linalg.pinv(predicted_covariances[position + 1])
        )
        smoothed_states[position] = filtered_states[position] + smoothing_gain @ (
            smoothed_states[position + 1] - predicted_states[position + 1]
        )

    level = _series(values, filtered_states[:, 0])
    quadrature = _series(values, filtered_states[:, 1])
    slope = (decay_rate * level + angular_frequency * quadrature).rename(values.name)
    acceleration = (
        (decay_rate**2 - angular_frequency**2) * level
        + 2.0 * decay_rate * angular_frequency * quadrature
    ).rename(values.name)
    amplitude = _series(
        values,
        np.hypot(filtered_states[:, 0], filtered_states[:, 1]),
    )
    angle_values = np.mod(
        np.degrees(np.arctan2(filtered_states[:, 1], filtered_states[:, 0])),
        360.0,
    )
    angle_values[angle_values >= 360.0] = 0.0
    angle = _series(values, angle_values)
    innovation = _series(values, innovations)
    uncertainty = _series(
        values,
        np.sqrt(np.maximum(filtered_covariances[:, 0, 0], 0.0)),
    )
    smoothed_level = _series(values, smoothed_states[:, 0])
    return HarmonicStateResult(
        level=level,
        quadrature=quadrature,
        slope=slope,
        acceleration=acceleration,
        amplitude=amplitude,
        angle=angle,
        innovation=innovation,
        uncertainty=uncertainty,
        smoothed_level=smoothed_level,
    )
