"""Causal local-level channel innovations."""

from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd


_RESULT_FIELDS = (
    "prediction",
    "state",
    "innovation",
    "prediction_uncertainty",
    "uncertainty",
)


def _copy_series(values: pd.Series) -> pd.Series:
    copied = values.copy(deep=True)
    copied.to_numpy(copy=False).setflags(write=False)
    return copied


@dataclass(frozen=True)
class LocalLevelResult:
    """Detached one-step predictions, residuals, and filtered states."""

    prediction: pd.Series
    state: pd.Series
    innovation: pd.Series
    prediction_uncertainty: pd.Series
    uncertainty: pd.Series

    def __post_init__(self) -> None:
        reference = object.__getattribute__(self, "state")
        if not isinstance(reference, pd.Series):
            raise TypeError("state must be a pandas Series")
        if reference.dtype != np.dtype("float64"):
            raise ValueError("result Series dtype must be float64")
        for field_name in _RESULT_FIELDS:
            values = object.__getattribute__(self, field_name)
            if not isinstance(values, pd.Series):
                raise TypeError(f"{field_name} must be a pandas Series")
            if not values.index.equals(reference.index):
                raise ValueError(f"{field_name} index must align with state")
            if values.index.names != reference.index.names:
                raise ValueError(f"{field_name} index names must align with state")
            if values.name != reference.name:
                raise ValueError(f"{field_name} name must match state")
            if values.dtype != np.dtype("float64"):
                raise ValueError(f"{field_name} dtype must be float64")
            object.__setattr__(self, field_name, _copy_series(values))

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


def _nonnegative_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _positive_real(value: object, name: str) -> float:
    numeric = _finite_real(value, name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _numeric_series(values: object) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise TypeError("values must be a pandas Series")
    if values.index.has_duplicates:
        raise ValueError("values index must be unique")
    if not values.index.is_monotonic_increasing:
        raise ValueError("values index must be monotonic increasing")
    normalized: list[float] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            normalized.append(np.nan)
            continue
        normalized.append(_finite_real(value, "values"))
    return pd.Series(
        normalized,
        index=values.index.copy(),
        name=values.name,
        dtype="float64",
    )


def _series(values: pd.Series, data: np.ndarray) -> pd.Series:
    return pd.Series(
        data,
        index=values.index,
        name=values.name,
        dtype="float64",
    )


def local_level_innovations(
    values: pd.Series,
    *,
    process_variance: float = 0.05,
    observation_variance: float = 0.25,
    initial_state: float = 0.0,
    initial_variance: float = 1.0,
) -> LocalLevelResult:
    """Filter a one-sided local-level model and return one-step residuals."""

    series = _numeric_series(values)
    process = _nonnegative_real(process_variance, "process_variance")
    observation = _positive_real(
        observation_variance,
        "observation_variance",
    )
    prior_state = _finite_real(initial_state, "initial_state")
    prior_variance = _positive_real(initial_variance, "initial_variance")
    count = len(series)
    predictions = np.full(count, np.nan, dtype="float64")
    states = np.full(count, np.nan, dtype="float64")
    innovations = np.full(count, np.nan, dtype="float64")
    prediction_uncertainties = np.full(count, np.nan, dtype="float64")
    uncertainties = np.full(count, np.nan, dtype="float64")
    initialized = False
    state = prior_state
    variance = prior_variance

    for position, observed_value in enumerate(series.to_numpy(dtype="float64")):
        if not initialized and not np.isfinite(observed_value):
            continue
        predicted_state = state
        predicted_variance = variance + process
        predictions[position] = predicted_state
        prediction_uncertainties[position] = np.sqrt(
            predicted_variance + observation
        )
        if np.isfinite(observed_value):
            residual = observed_value - predicted_state
            innovation_variance = predicted_variance + observation
            gain = predicted_variance / innovation_variance
            state = predicted_state + gain * residual
            variance = max((1.0 - gain) * predicted_variance, 0.0)
            innovations[position] = residual
            initialized = True
        else:
            state = predicted_state
            variance = predicted_variance
        states[position] = state
        uncertainties[position] = np.sqrt(variance)

    return LocalLevelResult(
        prediction=_series(series, predictions),
        state=_series(series, states),
        innovation=_series(series, innovations),
        prediction_uncertainty=_series(series, prediction_uncertainties),
        uncertainty=_series(series, uncertainties),
    )


__all__ = ["LocalLevelResult", "local_level_innovations"]
