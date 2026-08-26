"""Champion cycle-phase forecasts from governed causal harmonic states."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from numbers import Integral, Real
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from seven_cycle_platform.cycles.phase import CyclePhase
from seven_cycle_platform.registry.models import CycleSpec, IndicatorSpec


CYCLE_STATE_COLUMNS = (
    "as_of",
    "state_date",
    "visible_date",
    "data_vintage",
    "cycle_id",
    "status",
    "unavailable_reason",
    "level",
    "quadrature",
    "covariance_00",
    "covariance_01",
    "covariance_11",
    "phase_velocity",
    "acceleration",
    "phase_duration_months",
    "confidence",
    "center_period",
    "state_model_version",
    "state_config_hash",
)
LEADING_SIGNAL_COLUMNS = (
    "as_of",
    "observation_date",
    "release_date",
    "visible_date",
    "cycle_id",
    "indicator_id",
    "signal_value",
    "direction_prior",
)
CALIBRATION_HISTORY_COLUMNS = (
    "forecast_origin",
    "target_date",
    "cycle_id",
    "horizon_months",
    "raw_expansion_probability",
    "raw_downturn_probability",
    "raw_contraction_probability",
    "raw_recovery_probability",
    "realized_phase",
    "fold_id",
)
CYCLE_MONTHLY_PATH_COLUMNS = (
    "forecast_origin",
    "date",
    "cycle_id",
    "draw_id",
    "month_number",
    "level",
    "quadrature",
    "slope",
    "angle_degrees",
    "angle_unwrapped_degrees",
    "angle_anchor_degrees",
    "phase",
    "origin_phase",
    "origin_slope",
    "is_phase_transition",
    "is_slope_turn",
    "is_first_turn",
    "analytic_uncertainty",
    "base_phase_velocity",
    "effective_phase_velocity",
    "phase_velocity_adjustment",
    "acceleration_adjustment",
    "duration_adjustment",
    "leading_adjustment",
    "model_role",
    "forecast_model_version",
    "forecast_config_hash",
    "registry_hash",
    "state_model_version",
    "state_config_hash",
    "data_vintage",
)
CYCLE_FORECAST_SUMMARY_COLUMNS = (
    "as_of",
    "forecast_date",
    "cycle_id",
    "horizon_months",
    "status",
    "unavailable_reason",
    "raw_expansion_probability",
    "raw_downturn_probability",
    "raw_contraction_probability",
    "raw_recovery_probability",
    "expansion_probability",
    "downturn_probability",
    "contraction_probability",
    "recovery_probability",
    "angle_anchor_degrees",
    "angle_q10",
    "angle_q25",
    "angle_q50",
    "angle_q75",
    "angle_q90",
    "turning_status",
    "turning_probability",
    "turning_start_month",
    "turning_end_month",
    "turning_median_month",
    "turning_start_date",
    "turning_end_date",
    "turning_median_date",
    "forecast_uncertainty",
    "draw_count",
    "probability_support_count",
    "leading_signal_count",
    "leading_indicator_ids",
    "phase_velocity_adjustment",
    "acceleration_adjustment",
    "duration_adjustment",
    "leading_adjustment",
    "calibration_method",
    "calibration_version",
    "calibration_sample_count",
    "calibration_reason",
    "model_role",
    "forecast_model_version",
    "forecast_config_hash",
    "registry_hash",
    "state_model_version",
    "state_config_hash",
    "data_vintage",
)

_EXPECTED_CYCLE_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
_PHASES = tuple(phase.value for phase in CyclePhase)
_STATE_NUMERIC_COLUMNS = (
    "level",
    "quadrature",
    "covariance_00",
    "covariance_01",
    "covariance_11",
    "phase_velocity",
    "acceleration",
    "phase_duration_months",
    "confidence",
    "center_period",
)
_RESULT_FRAME_FIELDS = frozenset({"summary", "monthly_paths"})
_PATH_NUMERIC_COLUMNS = (
    "level",
    "quadrature",
    "slope",
    "angle_degrees",
    "angle_unwrapped_degrees",
    "angle_anchor_degrees",
    "origin_slope",
    "analytic_uncertainty",
    "base_phase_velocity",
    "effective_phase_velocity",
    "phase_velocity_adjustment",
    "acceleration_adjustment",
    "duration_adjustment",
    "leading_adjustment",
)


def _positive_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a positive integer")
    numeric = int(value)
    if numeric < 1:
        raise ValueError(f"{name} must be a positive integer")
    return numeric


def _nonnegative_integer(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Integral, np.integer),
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    numeric = int(value)
    if numeric < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return numeric


def _finite_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _bounded_fraction(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return numeric


def _positive_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _normalize_date(value: object, *, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    if not isinstance(value, (str, date, datetime, np.datetime64, pd.Timestamp)):
        raise TypeError(f"{name} must be date-like")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot be missing")
    if timestamp.tzinfo is not None:
        raise ValueError(f"{name} must be timezone-naive")
    return timestamp.normalize()


def _normalize_dates(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_date(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _required_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    if tuple(values.columns) != columns:
        raise ValueError(f"{name} columns do not match the forecast contract")
    return values.copy(deep=True)


def _cycle_number(cycle_id: str) -> int:
    return int(cycle_id.removeprefix("C"))


def _normalize_cycle_specs(values: object) -> tuple[CycleSpec, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("cycle_specs must be a sequence of CycleSpec objects")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "cycle_specs must be a sequence of CycleSpec objects"
        ) from error
    if any(not isinstance(cycle, CycleSpec) for cycle in supplied):
        raise TypeError("cycle_specs must contain only CycleSpec objects")
    cycle_ids = [cycle.cycle_id for cycle in supplied]
    if len(cycle_ids) != len(set(cycle_ids)):
        raise ValueError("cycle_specs contain duplicate cycle_id values")
    if set(cycle_ids) != set(_EXPECTED_CYCLE_IDS) or len(cycle_ids) != 7:
        raise ValueError("cycle_specs must contain exactly C1 through C7")
    return tuple(
        cycle.model_copy(deep=True)
        for cycle in sorted(supplied, key=lambda cycle: _cycle_number(cycle.cycle_id))
    )


def _normalize_indicator_specs(values: object) -> tuple[IndicatorSpec, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("indicator_specs must be a sequence of IndicatorSpec objects")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "indicator_specs must be a sequence of IndicatorSpec objects"
        ) from error
    if any(not isinstance(indicator, IndicatorSpec) for indicator in supplied):
        raise TypeError("indicator_specs must contain only IndicatorSpec objects")
    indicator_ids = [indicator.indicator_id for indicator in supplied]
    if len(indicator_ids) != len(set(indicator_ids)):
        raise ValueError("indicator_specs contain duplicate indicator_id values")
    return tuple(
        indicator.model_copy(deep=True)
        for indicator in sorted(supplied, key=lambda indicator: indicator.indicator_id)
    )


def _is_missing(value: object) -> bool:
    missing = pd.isna(value)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _normalize_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


def _normalize_optional_text(value: object, *, name: str) -> str | None:
    if _is_missing(value):
        return None
    return _normalize_text(value, name=name)


def _validate_hash(value: object, *, name: str) -> str:
    normalized = _normalize_text(value, name=name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _normalize_states(
    values: object,
    *,
    as_of: pd.Timestamp,
    cycle_specs: tuple[CycleSpec, ...],
) -> pd.DataFrame:
    states = _required_frame(values, name="states", columns=CYCLE_STATE_COLUMNS)
    if states.empty:
        raise ValueError("states must contain exactly one row per cycle")
    for column in ("as_of", "state_date", "visible_date", "data_vintage"):
        states[column] = _normalize_dates(states[column], name=f"states {column}")
    if set(states["as_of"]) != {as_of}:
        raise ValueError("every state as_of must equal CycleForecastInput.as_of")
    if bool((states["state_date"] > as_of).any()):
        raise ValueError("state_date cannot follow as_of")
    if bool((states["visible_date"] > as_of).any()):
        raise ValueError("visible_date cannot follow as_of")
    if bool((states["data_vintage"] > as_of).any()):
        raise ValueError("data_vintage cannot follow as_of")
    if bool((states["state_date"] > states["visible_date"]).any()):
        raise ValueError("state_date cannot follow visible_date")

    cycle_ids = states["cycle_id"].tolist()
    if any(not isinstance(cycle_id, str) for cycle_id in cycle_ids):
        raise TypeError("state cycle_id values must be strings")
    if len(cycle_ids) != len(set(cycle_ids)):
        raise ValueError("states contain duplicate cycle_id values")
    if set(cycle_ids) != set(_EXPECTED_CYCLE_IDS) or len(cycle_ids) != 7:
        raise ValueError("states must contain exactly one row for C1 through C7")

    specifications = {cycle.cycle_id: cycle for cycle in cycle_specs}
    normalized_rows: list[dict[str, object]] = []
    for row in states.to_dict(orient="records"):
        cycle_id = str(row["cycle_id"])
        specification = specifications[cycle_id]
        status = _normalize_text(row["status"], name="state status")
        if status not in {"available", "unavailable"}:
            raise ValueError("state status must be available or unavailable")
        reason = _normalize_optional_text(
            row["unavailable_reason"],
            name="unavailable_reason",
        )
        if status == "available" and reason is not None:
            raise ValueError("available states cannot define unavailable_reason")
        if status == "unavailable" and reason is None:
            raise ValueError("unavailable states require unavailable_reason")

        if status == "unavailable":
            if any(not _is_missing(row[column]) for column in _STATE_NUMERIC_COLUMNS):
                raise ValueError("unavailable state numeric fields must all be missing")
        else:
            numeric = {
                column: _finite_real(row[column], name=f"state {column}")
                for column in _STATE_NUMERIC_COLUMNS
            }
            covariance = np.asarray(
                [
                    [numeric["covariance_00"], numeric["covariance_01"]],
                    [numeric["covariance_01"], numeric["covariance_11"]],
                ],
                dtype="float64",
            )
            eigenvalues = np.linalg.eigvalsh(covariance)
            scale = max(1.0, float(np.max(np.abs(eigenvalues))))
            if eigenvalues.min() < -1e-10 * scale:
                raise ValueError("state covariance must be positive semidefinite")
            if numeric["covariance_00"] < 0.0 or numeric["covariance_11"] < 0.0:
                raise ValueError("state covariance diagonal must be nonnegative")
            if numeric["phase_velocity"] <= 0.0:
                raise ValueError("state phase_velocity must be positive")
            if numeric["phase_duration_months"] <= 0.0:
                raise ValueError("state phase_duration_months must be positive")
            if not 0.0 <= numeric["confidence"] <= 1.0:
                raise ValueError("state confidence must be between 0 and 1")
            if not (
                float(specification.search_min)
                <= numeric["center_period"]
                <= float(specification.search_max)
            ):
                raise ValueError(
                    "state center_period must lie in its registry search band"
                )
            row.update(numeric)

        row["status"] = status
        row["unavailable_reason"] = reason
        row["state_model_version"] = _normalize_text(
            row["state_model_version"],
            name="state_model_version",
        )
        row["state_config_hash"] = _validate_hash(
            row["state_config_hash"],
            name="state_config_hash",
        )
        normalized_rows.append(row)

    normalized = pd.DataFrame(normalized_rows, columns=CYCLE_STATE_COLUMNS)
    normalized["_cycle_order"] = normalized["cycle_id"].map(_cycle_number)
    return (
        normalized.sort_values("_cycle_order", kind="stable")
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )


def _normalize_leading_signals(
    values: object,
    *,
    as_of: pd.Timestamp,
    cycle_specs: tuple[CycleSpec, ...],
    indicator_specs: tuple[IndicatorSpec, ...],
) -> pd.DataFrame:
    signals = _required_frame(
        values,
        name="leading_signals",
        columns=LEADING_SIGNAL_COLUMNS,
    )
    if signals.empty:
        return signals.reset_index(drop=True)
    for column in ("as_of", "observation_date", "release_date", "visible_date"):
        signals[column] = _normalize_dates(
            signals[column],
            name=f"leading_signals {column}",
        )
    if set(signals["as_of"]) != {as_of}:
        raise ValueError("every leading signal as_of must equal the forecast as_of")
    if bool((signals["observation_date"] > signals["release_date"]).any()):
        raise ValueError("leading signal observation_date cannot follow release_date")
    if bool((signals["release_date"] > signals["visible_date"]).any()):
        raise ValueError("leading signal release_date cannot follow visible_date")
    if bool((signals["visible_date"] > as_of).any()):
        raise ValueError("future-visible leading signals are not allowed")

    known_cycles = {cycle.cycle_id for cycle in cycle_specs}
    indicators = {indicator.indicator_id: indicator for indicator in indicator_specs}
    normalized_values: list[float] = []
    normalized_priors: list[float] = []
    for row in signals.itertuples(index=False):
        if not isinstance(row.cycle_id, str) or row.cycle_id not in known_cycles:
            raise ValueError("leading signal cycle_id is not registered")
        if not isinstance(row.indicator_id, str) or row.indicator_id not in indicators:
            raise ValueError("leading signal indicator_id is not registered")
        indicator = indicators[row.indicator_id]
        if not indicator.active:
            raise ValueError("leading signals must use active indicators")
        if indicator.timing != "leading":
            raise ValueError(
                "leading signals cannot use coincident or lagging indicators"
            )
        if row.cycle_id not in indicator.allowed_cycles:
            raise ValueError("leading signal indicator is not approved for the cycle")
        if indicator.direction_prior is None:
            raise ValueError(
                "leading signal indicators require an explicit direction prior"
            )
        signal_value = _finite_real(row.signal_value, name="signal_value")
        direction_prior = _finite_real(
            row.direction_prior,
            name="direction_prior",
        )
        if not np.isclose(
            direction_prior,
            float(indicator.direction_prior),
            atol=1e-12,
            rtol=1e-12,
        ):
            raise ValueError("leading signal direction_prior must match the registry")
        normalized_values.append(signal_value)
        normalized_priors.append(direction_prior)
    signals["signal_value"] = pd.Series(
        normalized_values,
        index=signals.index,
        dtype="float64",
    )
    signals["direction_prior"] = pd.Series(
        normalized_priors,
        index=signals.index,
        dtype="float64",
    )
    if signals.duplicated(["cycle_id", "indicator_id", "observation_date"]).any():
        raise ValueError("leading signals contain duplicate observations")
    return signals.sort_values(
        ["cycle_id", "indicator_id", "observation_date"],
        kind="stable",
    ).reset_index(drop=True)


def _forecast_date(origin: pd.Timestamp, horizon_months: int) -> pd.Timestamp:
    first = origin + pd.offsets.MonthEnd(1)
    return first + pd.offsets.MonthEnd(horizon_months - 1)


def _normalize_calibration_history(
    values: object,
    *,
    as_of: pd.Timestamp,
    cycle_specs: tuple[CycleSpec, ...],
) -> pd.DataFrame:
    history = _required_frame(
        values,
        name="calibration_history",
        columns=CALIBRATION_HISTORY_COLUMNS,
    )
    if history.empty:
        return history.reset_index(drop=True)
    history["forecast_origin"] = _normalize_dates(
        history["forecast_origin"],
        name="calibration forecast_origin",
    )
    history["target_date"] = _normalize_dates(
        history["target_date"],
        name="calibration target_date",
    )
    if bool((history["forecast_origin"] >= as_of).any()):
        raise ValueError("calibration folds must originate strictly before as_of")
    if bool((history["target_date"] > as_of).any()):
        raise ValueError("future calibration outcomes are not allowed")
    if bool((history["forecast_origin"] >= history["target_date"]).any()):
        raise ValueError("calibration target_date must follow forecast_origin")

    horizon_lookup = {cycle.cycle_id: set(cycle.horizons) for cycle in cycle_specs}
    probability_columns = [f"raw_{phase}_probability" for phase in _PHASES]
    normalized_horizons: list[int] = []
    normalized_fold_ids: list[str] = []
    for row in history.itertuples(index=False):
        if not isinstance(row.cycle_id, str) or row.cycle_id not in horizon_lookup:
            raise ValueError("calibration history contains an unknown cycle_id")
        horizon = _positive_integer(
            row.horizon_months,
            name="calibration horizon_months",
        )
        if horizon not in horizon_lookup[row.cycle_id]:
            raise ValueError("calibration horizon is not registered for the cycle")
        if row.target_date != _forecast_date(row.forecast_origin, horizon):
            raise ValueError("calibration target_date must match its horizon")
        if row.realized_phase not in _PHASES:
            raise ValueError("calibration realized_phase is not governed")
        normalized_fold_ids.append(
            _normalize_text(row.fold_id, name="calibration fold_id")
        )
        normalized_horizons.append(horizon)
    history["horizon_months"] = pd.Series(
        normalized_horizons,
        index=history.index,
        dtype="int64",
    )
    history["fold_id"] = pd.Series(
        normalized_fold_ids,
        index=history.index,
        dtype="object",
    )
    probabilities = np.asarray(
        [
            [_finite_real(value, name=column) for value in history[column].tolist()]
            for column in probability_columns
        ],
        dtype="float64",
    ).T
    if bool(((probabilities < 0.0) | (probabilities > 1.0)).any()):
        raise ValueError("calibration raw probabilities must be between 0 and 1")
    if not np.allclose(
        probabilities.sum(axis=1),
        1.0,
        atol=1e-10,
        rtol=1e-10,
    ):
        raise ValueError("calibration raw probabilities must sum to one")
    for position, column in enumerate(probability_columns):
        history[column] = probabilities[:, position]
    if history.duplicated(["forecast_origin", "cycle_id", "horizon_months"]).any():
        raise ValueError("calibration history contains duplicate forecast folds")
    if history.duplicated(["cycle_id", "horizon_months", "fold_id"]).any():
        raise ValueError("calibration history contains an overlapping calibration fold")
    return history.sort_values(
        ["target_date", "forecast_origin", "cycle_id", "horizon_months"],
        kind="stable",
    ).reset_index(drop=True)


@dataclass(frozen=True)
class CycleForecastConfig:
    """Immutable Champion simulation and bounded-adjustment configuration."""

    draw_count: int = 2_000
    seed: int = 0
    half_life_cycles: float = 2.0
    process_noise_scale: float = 0.08
    max_phase_velocity_fraction: float = 0.35
    max_acceleration_fraction: float = 0.15
    max_duration_fraction: float = 0.10
    max_leading_fraction: float = 0.15
    min_calibration_samples: int = 24
    min_calibration_class_count: int = 3
    calibration_method: str = "logistic"
    calibration_regularization: float = 1.0
    model_version: str = "cycle-champion-v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "draw_count",
            _positive_integer(self.draw_count, name="draw_count"),
        )
        object.__setattr__(
            self,
            "seed",
            _nonnegative_integer(self.seed, name="seed"),
        )
        object.__setattr__(
            self,
            "half_life_cycles",
            _positive_real(self.half_life_cycles, name="half_life_cycles"),
        )
        object.__setattr__(
            self,
            "process_noise_scale",
            _positive_real(self.process_noise_scale, name="process_noise_scale"),
        )
        for field_name in (
            "max_phase_velocity_fraction",
            "max_acceleration_fraction",
            "max_duration_fraction",
            "max_leading_fraction",
        ):
            object.__setattr__(
                self,
                field_name,
                _bounded_fraction(getattr(self, field_name), name=field_name),
            )
        object.__setattr__(
            self,
            "min_calibration_samples",
            _positive_integer(
                self.min_calibration_samples,
                name="min_calibration_samples",
            ),
        )
        object.__setattr__(
            self,
            "min_calibration_class_count",
            _positive_integer(
                self.min_calibration_class_count,
                name="min_calibration_class_count",
            ),
        )
        if self.calibration_method not in {"logistic", "isotonic"}:
            raise ValueError("calibration_method must be logistic or isotonic")
        object.__setattr__(
            self,
            "calibration_regularization",
            _positive_real(
                self.calibration_regularization,
                name="calibration_regularization",
            ),
        )
        object.__setattr__(
            self,
            "model_version",
            _normalize_text(self.model_version, name="model_version"),
        )


@dataclass(frozen=True)
class CycleForecastInput:
    """Point-in-time state, registry, leading-signal, and calibration inputs.

    ``phase_velocity`` is positive clockwise radians per month. ``acceleration``
    is a signed level-acceleration signal regularized against current state scale.
    The three covariance fields are the explicit symmetric 2 by 2 covariance of
    ``(level, quadrature)``; no scalar uncertainty field is inferred as covariance.
    Leading ``signal_value`` inputs are standardized signed observations whose
    explicit ``direction_prior`` must exactly match the governed indicator registry.
    """

    as_of: date
    cycle_specs: Sequence[CycleSpec]
    indicator_specs: Sequence[IndicatorSpec]
    states: pd.DataFrame
    leading_signals: pd.DataFrame
    calibration_history: pd.DataFrame

    def __post_init__(self) -> None:
        as_of = _normalize_date(self.as_of, name="as_of")
        cycle_specs = _normalize_cycle_specs(
            object.__getattribute__(self, "cycle_specs")
        )
        indicator_specs = _normalize_indicator_specs(
            object.__getattribute__(self, "indicator_specs")
        )
        states = _normalize_states(
            object.__getattribute__(self, "states"),
            as_of=as_of,
            cycle_specs=cycle_specs,
        )
        leading_signals = _normalize_leading_signals(
            object.__getattribute__(self, "leading_signals"),
            as_of=as_of,
            cycle_specs=cycle_specs,
            indicator_specs=indicator_specs,
        )
        calibration_history = _normalize_calibration_history(
            object.__getattribute__(self, "calibration_history"),
            as_of=as_of,
            cycle_specs=cycle_specs,
        )
        object.__setattr__(self, "as_of", as_of.date())
        object.__setattr__(self, "cycle_specs", cycle_specs)
        object.__setattr__(self, "indicator_specs", indicator_specs)
        object.__setattr__(self, "states", states.copy(deep=True))
        object.__setattr__(self, "leading_signals", leading_signals.copy(deep=True))
        object.__setattr__(
            self,
            "calibration_history",
            calibration_history.copy(deep=True),
        )

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in {"states", "leading_signals", "calibration_history"} and isinstance(
            value,
            pd.DataFrame,
        ):
            return value.copy(deep=True)
        if name == "cycle_specs" and isinstance(value, tuple):
            return tuple(cycle.model_copy(deep=True) for cycle in value)
        if name == "indicator_specs" and isinstance(value, tuple):
            return tuple(indicator.model_copy(deep=True) for indicator in value)
        return value


def _stable_hash(payload: object) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _config_hash(config: CycleForecastConfig) -> str:
    return _stable_hash(asdict(config))


def _registry_hash(forecast_input: CycleForecastInput) -> str:
    cycle_specs = object.__getattribute__(forecast_input, "cycle_specs")
    indicator_specs = object.__getattribute__(forecast_input, "indicator_specs")
    return _stable_hash(
        {
            "cycles": [cycle.model_dump(mode="json") for cycle in cycle_specs],
            "indicators": [
                indicator.model_dump(mode="json") for indicator in indicator_specs
            ],
        }
    )


def _matrix_sqrt(covariance: np.ndarray) -> np.ndarray:
    symmetric = (covariance + covariance.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.maximum(eigenvalues, 0.0)
    return eigenvectors @ np.diag(np.sqrt(clipped)) @ eigenvectors.T


def _phase_labels(level: np.ndarray, slope: np.ndarray) -> np.ndarray:
    labels = np.full(level.shape, CyclePhase.RECOVERY.value, dtype=object)
    labels[(level >= 0.0) & (slope >= 0.0)] = CyclePhase.EXPANSION.value
    labels[(level >= 0.0) & (slope < 0.0)] = CyclePhase.DOWNTURN.value
    labels[(level < 0.0) & (slope < 0.0)] = CyclePhase.CONTRACTION.value
    return labels


def _cycle_adjustments(
    state: pd.Series,
    cycle: CycleSpec,
    signals: pd.DataFrame,
    config: CycleForecastConfig,
) -> dict[str, float]:
    period_months = float(state["center_period"])
    if cycle.frequency == "A":
        period_months *= 12.0
    base_velocity = 2.0 * np.pi / period_months
    supplied_velocity = float(state["phase_velocity"])
    velocity_ratio = supplied_velocity / base_velocity - 1.0
    velocity_adjustment = float(
        np.clip(
            velocity_ratio,
            -config.max_phase_velocity_fraction,
            config.max_phase_velocity_fraction,
        )
    )
    state_scale = max(
        float(np.hypot(state["level"], state["quadrature"])),
        float(np.sqrt(state["covariance_00"] + state["covariance_11"])),
        0.1,
    )
    acceleration_score = float(np.tanh(float(state["acceleration"]) / state_scale))
    acceleration_adjustment = config.max_acceleration_fraction * acceleration_score
    expected_duration = max(period_months / 4.0, 1.0)
    duration_score = float(
        np.tanh(
            (float(state["phase_duration_months"]) - expected_duration)
            / expected_duration
        )
    )
    duration_adjustment = config.max_duration_fraction * duration_score
    if signals.empty:
        leading_score = 0.0
    else:
        signed = signals["signal_value"].to_numpy(dtype="float64") * signals[
            "direction_prior"
        ].to_numpy(dtype="float64")
        shrinkage = np.sqrt(len(signed)) / (1.0 + np.sqrt(len(signed)))
        leading_score = float(np.tanh(float(np.mean(signed))) * shrinkage)
    leading_adjustment = config.max_leading_fraction * leading_score
    return {
        "period_months": period_months,
        "base_velocity": base_velocity,
        "state_scale": state_scale,
        "velocity_adjustment": velocity_adjustment,
        "acceleration_adjustment": acceleration_adjustment,
        "duration_adjustment": duration_adjustment,
        "leading_adjustment": leading_adjustment,
    }


def _simulate_cycle_paths(
    *,
    state: pd.Series,
    cycle: CycleSpec,
    signals: pd.DataFrame,
    as_of: pd.Timestamp,
    config: CycleForecastConfig,
    forecast_config_hash: str,
    registry_hash: str,
) -> list[dict[str, object]]:
    adjustments = _cycle_adjustments(state, cycle, signals, config)
    period_months = adjustments["period_months"]
    base_velocity = adjustments["base_velocity"]
    damping = 0.5 ** (1.0 / (config.half_life_cycles * period_months))
    decay_rate = float(np.log(damping))
    covariance = np.asarray(
        [
            [state["covariance_00"], state["covariance_01"]],
            [state["covariance_01"], state["covariance_11"]],
        ],
        dtype="float64",
    )
    mean = np.asarray([state["level"], state["quadrature"]], dtype="float64")
    seed_sequence = np.random.SeedSequence(
        [config.seed, _cycle_number(cycle.cycle_id), 24]
    )
    generator = np.random.default_rng(seed_sequence)
    draw_states = mean + generator.standard_normal((config.draw_count, 2)) @ (
        _matrix_sqrt(covariance).T
    )
    initial_variance = max(float(np.trace(covariance)) / 2.0, 1e-6)
    structural_factor = 1.0 + 0.75 * min(period_months / 240.0, 1.0)
    confidence_factor = 1.0 + 1.5 * (1.0 - float(state["confidence"]))
    process_variance = (
        config.process_noise_scale
        * (initial_variance + 0.02 * adjustments["state_scale"] ** 2 + 0.0025)
        * structural_factor
        * confidence_factor
    )
    process_covariance = np.eye(2, dtype="float64") * process_variance
    process_standard_deviation = float(np.sqrt(process_variance))
    propagated_covariance = covariance.copy()
    previous_uncertainty = float(np.sqrt(max(float(np.trace(covariance)), 0.0)))

    anchor_angle = float(np.mod(np.degrees(np.arctan2(mean[1], mean[0])), 360.0))
    initial_angles = np.mod(
        np.degrees(np.arctan2(draw_states[:, 1], draw_states[:, 0])),
        360.0,
    )
    previous_angles = initial_angles
    unwrapped_angles = anchor_angle + (
        (initial_angles - anchor_angle + 180.0) % 360.0 - 180.0
    )
    leading_force = (
        adjustments["leading_adjustment"]
        * adjustments["state_scale"]
        * np.asarray([0.06, 0.04], dtype="float64")
    )
    first_velocity = base_velocity * (
        1.0
        + adjustments["velocity_adjustment"]
        + adjustments["acceleration_adjustment"]
        + adjustments["duration_adjustment"]
        + 0.25 * adjustments["leading_adjustment"]
    )
    first_velocity = float(
        np.clip(first_velocity, 0.4 * base_velocity, 1.6 * base_velocity)
    )
    origin_slopes = (
        decay_rate * draw_states[:, 0]
        + first_velocity * draw_states[:, 1]
        + leading_force[0]
    )
    origin_phases = _phase_labels(draw_states[:, 0], origin_slopes)
    first_turn_seen = np.zeros(config.draw_count, dtype=bool)
    maximum_horizon = max(cycle.horizons)
    records: list[dict[str, object]] = []

    for month_number in range(1, maximum_horizon + 1):
        acceleration_decay = np.exp(
            -(month_number - 1) / max(float(state["phase_duration_months"]), 1.0)
        )
        effective_velocity = base_velocity * (
            1.0
            + adjustments["velocity_adjustment"]
            + adjustments["duration_adjustment"]
            + adjustments["acceleration_adjustment"] * acceleration_decay
            + 0.25 * adjustments["leading_adjustment"]
        )
        effective_velocity = float(
            np.clip(effective_velocity, 0.4 * base_velocity, 1.6 * base_velocity)
        )
        transition = damping * np.asarray(
            [
                [np.cos(effective_velocity), np.sin(effective_velocity)],
                [-np.sin(effective_velocity), np.cos(effective_velocity)],
            ],
            dtype="float64",
        )
        propagated_covariance = (
            transition @ propagated_covariance @ transition.T + process_covariance
        )
        acceleration_force = (
            adjustments["acceleration_adjustment"]
            * acceleration_decay
            * adjustments["state_scale"]
            * np.asarray([0.01, 0.03], dtype="float64")
        )
        innovations = generator.standard_normal((config.draw_count, 2))
        draw_states = (
            draw_states @ transition.T
            + leading_force
            + acceleration_force
            + innovations * process_standard_deviation
        )
        level = draw_states[:, 0]
        quadrature = draw_states[:, 1]
        slope = decay_rate * level + effective_velocity * quadrature + leading_force[0]
        phase = _phase_labels(level, slope)
        angles = np.mod(
            np.degrees(np.arctan2(quadrature, level)),
            360.0,
        )
        angle_delta = (angles - previous_angles + 180.0) % 360.0 - 180.0
        unwrapped_angles = unwrapped_angles + angle_delta
        previous_angles = angles
        phase_transition = phase != origin_phases
        slope_turn = (slope >= 0.0) != (origin_slopes >= 0.0)
        first_turn = (phase_transition | slope_turn) & ~first_turn_seen
        first_turn_seen |= first_turn
        propagated_uncertainty = float(
            np.sqrt(max(float(np.trace(propagated_covariance)), 0.0))
        )
        conservative_uncertainty = float(
            np.sqrt(
                max(float(np.trace(covariance)), 0.0)
                + 2.0 * process_variance * month_number
            )
        )
        analytic_uncertainty = max(
            previous_uncertainty,
            propagated_uncertainty,
            conservative_uncertainty,
        )
        previous_uncertainty = analytic_uncertainty
        forecast_date = _forecast_date(as_of, month_number)
        for draw_id in range(config.draw_count):
            records.append(
                {
                    "forecast_origin": as_of,
                    "date": forecast_date,
                    "cycle_id": cycle.cycle_id,
                    "draw_id": draw_id,
                    "month_number": month_number,
                    "level": float(level[draw_id]),
                    "quadrature": float(quadrature[draw_id]),
                    "slope": float(slope[draw_id]),
                    "angle_degrees": float(angles[draw_id]),
                    "angle_unwrapped_degrees": float(unwrapped_angles[draw_id]),
                    "angle_anchor_degrees": anchor_angle,
                    "phase": str(phase[draw_id]),
                    "origin_phase": str(origin_phases[draw_id]),
                    "origin_slope": float(origin_slopes[draw_id]),
                    "is_phase_transition": bool(phase_transition[draw_id]),
                    "is_slope_turn": bool(slope_turn[draw_id]),
                    "is_first_turn": bool(first_turn[draw_id]),
                    "analytic_uncertainty": analytic_uncertainty,
                    "base_phase_velocity": base_velocity,
                    "effective_phase_velocity": effective_velocity,
                    "phase_velocity_adjustment": adjustments["velocity_adjustment"],
                    "acceleration_adjustment": adjustments["acceleration_adjustment"],
                    "duration_adjustment": adjustments["duration_adjustment"],
                    "leading_adjustment": adjustments["leading_adjustment"],
                    "model_role": "champion",
                    "forecast_model_version": config.model_version,
                    "forecast_config_hash": forecast_config_hash,
                    "registry_hash": registry_hash,
                    "state_model_version": state["state_model_version"],
                    "state_config_hash": state["state_config_hash"],
                    "data_vintage": state["data_vintage"],
                }
            )
    return records


def _turning_summary(
    cycle_paths: pd.DataFrame,
    *,
    horizon: int,
    draw_count: int,
) -> dict[str, object]:
    first_turns = cycle_paths.loc[
        cycle_paths["is_first_turn"] & cycle_paths["month_number"].le(horizon),
        ["draw_id", "month_number", "date"],
    ]
    if first_turns.empty:
        return {
            "turning_status": "none",
            "turning_probability": 0.0,
            "turning_start_month": None,
            "turning_end_month": None,
            "turning_median_month": None,
            "turning_start_date": pd.NaT,
            "turning_end_date": pd.NaT,
            "turning_median_date": pd.NaT,
        }
    months = first_turns["month_number"].to_numpy(dtype="float64")
    start_month = int(np.ceil(np.quantile(months, 0.10)))
    end_month = int(np.ceil(np.quantile(months, 0.90)))
    median_month = int(np.ceil(np.quantile(months, 0.50)))
    date_lookup = (
        cycle_paths[["month_number", "date"]]
        .drop_duplicates("month_number")
        .set_index("month_number")["date"]
    )
    return {
        "turning_status": "available",
        "turning_probability": float(first_turns["draw_id"].nunique() / draw_count),
        "turning_start_month": start_month,
        "turning_end_month": end_month,
        "turning_median_month": median_month,
        "turning_start_date": pd.Timestamp(date_lookup.loc[start_month]),
        "turning_end_date": pd.Timestamp(date_lookup.loc[end_month]),
        "turning_median_date": pd.Timestamp(date_lookup.loc[median_month]),
    }


def _identity_calibration(
    raw_probabilities: dict[str, float],
    *,
    sample_count: int,
    reason: str,
) -> tuple[dict[str, float], dict[str, object]]:
    return dict(raw_probabilities), {
        "calibration_method": "identity",
        "calibration_version": "identity-v1",
        "calibration_sample_count": sample_count,
        "calibration_reason": reason,
    }


def _calibrate_probabilities(
    raw_probabilities: dict[str, float],
    *,
    history: pd.DataFrame,
    config: CycleForecastConfig,
) -> tuple[dict[str, float], dict[str, object]]:
    sample_count = len(history)
    if sample_count < config.min_calibration_samples:
        return _identity_calibration(
            raw_probabilities,
            sample_count=sample_count,
            reason="insufficient_prior_folds",
        )

    realized = history["realized_phase"].to_numpy(dtype=object)
    for phase in _PHASES:
        positive_count = int(np.count_nonzero(realized == phase))
        negative_count = sample_count - positive_count
        if (
            positive_count < config.min_calibration_class_count
            or negative_count < config.min_calibration_class_count
        ):
            return _identity_calibration(
                raw_probabilities,
                sample_count=sample_count,
                reason="insufficient_class_support",
            )

    calibrated_values: list[float] = []
    try:
        for phase in _PHASES:
            training_probabilities = history[f"raw_{phase}_probability"].to_numpy(
                dtype="float64"
            )
            outcomes = (realized == phase).astype("int64")
            if config.calibration_method == "logistic":
                model = LogisticRegression(
                    C=1.0 / config.calibration_regularization,
                    max_iter=1_000,
                    random_state=config.seed,
                    solver="lbfgs",
                )
                model.fit(training_probabilities.reshape(-1, 1), outcomes)
                calibrated = float(
                    model.predict_proba(
                        np.asarray([[raw_probabilities[phase]]], dtype="float64")
                    )[0, 1]
                )
            else:
                model = IsotonicRegression(
                    y_min=0.0,
                    y_max=1.0,
                    out_of_bounds="clip",
                )
                model.fit(training_probabilities, outcomes)
                calibrated = float(model.predict([raw_probabilities[phase]])[0])
            calibrated_values.append(float(np.clip(calibrated, 0.0, 1.0)))
    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
        return _identity_calibration(
            raw_probabilities,
            sample_count=sample_count,
            reason="calibration_fit_failed",
        )

    calibrated_array = np.asarray(calibrated_values, dtype="float64")
    total = float(calibrated_array.sum())
    if not np.isfinite(calibrated_array).all() or total <= 0.0:
        return _identity_calibration(
            raw_probabilities,
            sample_count=sample_count,
            reason="calibration_fit_failed",
        )
    calibrated_array /= total
    calibrated_probabilities = {
        phase: float(calibrated_array[position])
        for position, phase in enumerate(_PHASES)
    }
    method = f"walk_forward_{config.calibration_method}"
    return calibrated_probabilities, {
        "calibration_method": method,
        "calibration_version": f"walk-forward-{config.calibration_method}-v1",
        "calibration_sample_count": sample_count,
        "calibration_reason": "calibrated",
    }


def _available_summary_row(
    *,
    state: pd.Series,
    cycle: CycleSpec,
    cycle_paths: pd.DataFrame,
    signals: pd.DataFrame,
    calibration_history: pd.DataFrame,
    horizon: int,
    as_of: pd.Timestamp,
    config: CycleForecastConfig,
) -> dict[str, object]:
    endpoint = cycle_paths.loc[cycle_paths["month_number"].eq(horizon)]
    raw_probabilities = {
        phase: float(endpoint["phase"].eq(phase).mean()) for phase in _PHASES
    }
    calibrated_probabilities, calibration_metadata = _calibrate_probabilities(
        raw_probabilities,
        history=calibration_history,
        config=config,
    )
    angle_quantiles = np.quantile(
        endpoint["angle_unwrapped_degrees"].to_numpy(dtype="float64"),
        [0.10, 0.25, 0.50, 0.75, 0.90],
    )
    first_path = cycle_paths.iloc[0]
    indicator_ids = "|".join(sorted(set(signals["indicator_id"])))
    row: dict[str, object] = {
        "as_of": as_of,
        "forecast_date": _forecast_date(as_of, horizon),
        "cycle_id": cycle.cycle_id,
        "horizon_months": horizon,
        "status": "available",
        "unavailable_reason": None,
        **{f"raw_{phase}_probability": raw_probabilities[phase] for phase in _PHASES},
        **{
            f"{phase}_probability": calibrated_probabilities[phase] for phase in _PHASES
        },
        "angle_anchor_degrees": float(first_path["angle_anchor_degrees"]),
        "angle_q10": float(angle_quantiles[0]),
        "angle_q25": float(angle_quantiles[1]),
        "angle_q50": float(angle_quantiles[2]),
        "angle_q75": float(angle_quantiles[3]),
        "angle_q90": float(angle_quantiles[4]),
        "forecast_uncertainty": float(endpoint["analytic_uncertainty"].iloc[0]),
        "draw_count": config.draw_count,
        "probability_support_count": config.draw_count,
        "leading_signal_count": len(signals),
        "leading_indicator_ids": indicator_ids,
        "phase_velocity_adjustment": float(first_path["phase_velocity_adjustment"]),
        "acceleration_adjustment": float(first_path["acceleration_adjustment"]),
        "duration_adjustment": float(first_path["duration_adjustment"]),
        "leading_adjustment": float(first_path["leading_adjustment"]),
        **calibration_metadata,
        "model_role": "champion",
        "forecast_model_version": first_path["forecast_model_version"],
        "forecast_config_hash": first_path["forecast_config_hash"],
        "registry_hash": first_path["registry_hash"],
        "state_model_version": state["state_model_version"],
        "state_config_hash": state["state_config_hash"],
        "data_vintage": state["data_vintage"],
    }
    row.update(
        _turning_summary(
            cycle_paths,
            horizon=horizon,
            draw_count=config.draw_count,
        )
    )
    return row


def _unavailable_summary_row(
    *,
    state: pd.Series,
    cycle: CycleSpec,
    horizon: int,
    as_of: pd.Timestamp,
    config: CycleForecastConfig,
    forecast_config_hash: str,
    registry_hash: str,
) -> dict[str, object]:
    missing_metrics = {
        name: np.nan
        for name in (
            *[f"raw_{phase}_probability" for phase in _PHASES],
            *[f"{phase}_probability" for phase in _PHASES],
            "angle_anchor_degrees",
            "angle_q10",
            "angle_q25",
            "angle_q50",
            "angle_q75",
            "angle_q90",
            "turning_probability",
            "forecast_uncertainty",
            "phase_velocity_adjustment",
            "acceleration_adjustment",
            "duration_adjustment",
            "leading_adjustment",
        )
    }
    return {
        "as_of": as_of,
        "forecast_date": _forecast_date(as_of, horizon),
        "cycle_id": cycle.cycle_id,
        "horizon_months": horizon,
        "status": "unavailable",
        "unavailable_reason": state["unavailable_reason"],
        **missing_metrics,
        "turning_status": "unavailable",
        "turning_start_month": None,
        "turning_end_month": None,
        "turning_median_month": None,
        "turning_start_date": pd.NaT,
        "turning_end_date": pd.NaT,
        "turning_median_date": pd.NaT,
        "draw_count": 0,
        "probability_support_count": 0,
        "leading_signal_count": 0,
        "leading_indicator_ids": "",
        "calibration_method": "identity",
        "calibration_version": "identity-v1",
        "calibration_sample_count": 0,
        "calibration_reason": "state_unavailable",
        "model_role": "champion",
        "forecast_model_version": config.model_version,
        "forecast_config_hash": forecast_config_hash,
        "registry_hash": registry_hash,
        "state_model_version": state["state_model_version"],
        "state_config_hash": state["state_config_hash"],
        "data_vintage": state["data_vintage"],
    }


def _build_summary(
    *,
    forecast_input: CycleForecastInput,
    monthly_paths: pd.DataFrame,
    config: CycleForecastConfig,
) -> pd.DataFrame:
    as_of = pd.Timestamp(forecast_input.as_of)
    states = object.__getattribute__(forecast_input, "states")
    cycle_specs = object.__getattribute__(forecast_input, "cycle_specs")
    leading_signals = object.__getattribute__(forecast_input, "leading_signals")
    calibration_history = object.__getattribute__(
        forecast_input,
        "calibration_history",
    )
    forecast_config_hash = _config_hash(config)
    registry_hash = _registry_hash(forecast_input)
    records: list[dict[str, object]] = []
    for cycle in cycle_specs:
        state = states.loc[states["cycle_id"].eq(cycle.cycle_id)].iloc[0]
        signals = leading_signals.loc[leading_signals["cycle_id"].eq(cycle.cycle_id)]
        cycle_paths = monthly_paths.loc[monthly_paths["cycle_id"].eq(cycle.cycle_id)]
        for horizon in cycle.horizons:
            if state["status"] == "unavailable":
                records.append(
                    _unavailable_summary_row(
                        state=state,
                        cycle=cycle,
                        horizon=horizon,
                        as_of=as_of,
                        config=config,
                        forecast_config_hash=forecast_config_hash,
                        registry_hash=registry_hash,
                    )
                )
            else:
                records.append(
                    _available_summary_row(
                        state=state,
                        cycle=cycle,
                        cycle_paths=cycle_paths,
                        signals=signals,
                        calibration_history=calibration_history.loc[
                            calibration_history["cycle_id"].eq(cycle.cycle_id)
                            & calibration_history["horizon_months"].eq(horizon)
                        ],
                        horizon=horizon,
                        as_of=as_of,
                        config=config,
                    )
                )
    return pd.DataFrame(records, columns=CYCLE_FORECAST_SUMMARY_COLUMNS)


def _validate_path_geometry(
    paths: pd.DataFrame,
    *,
    forecast_input: CycleForecastInput,
    config: CycleForecastConfig,
) -> None:
    if paths.empty:
        return
    try:
        numeric = paths.loc[:, _PATH_NUMERIC_COLUMNS].to_numpy(dtype="float64")
    except (TypeError, ValueError) as error:
        raise TypeError("monthly path state fields must be numeric") from error
    if not np.isfinite(numeric).all():
        raise ValueError("monthly path state fields must be finite")
    for position, column in enumerate(_PATH_NUMERIC_COLUMNS):
        paths[column] = numeric[:, position]

    for column in ("is_phase_transition", "is_slope_turn", "is_first_turn"):
        if any(
            not isinstance(value, (bool, np.bool_)) for value in paths[column].tolist()
        ):
            raise TypeError(f"monthly path {column} values must be boolean")
        paths[column] = paths[column].astype(bool)
    if not set(paths["phase"]).issubset(_PHASES):
        raise ValueError("monthly path phase values are not governed")
    if not set(paths["origin_phase"]).issubset(_PHASES):
        raise ValueError("monthly path origin_phase values are not governed")
    origin_groups = paths.groupby(["cycle_id", "draw_id"], sort=False)
    if bool(origin_groups["origin_phase"].nunique(dropna=False).gt(1).any()):
        raise ValueError("monthly path origin_phase must be constant within draw")
    if bool(origin_groups["origin_slope"].nunique(dropna=False).gt(1).any()):
        raise ValueError("monthly path origin_slope must be constant within draw")
    if not paths["angle_degrees"].between(0.0, 360.0, inclusive="left").all():
        raise ValueError("monthly path angle_degrees must be in [0, 360)")
    if (
        not paths["angle_anchor_degrees"]
        .between(
            0.0,
            360.0,
            inclusive="left",
        )
        .all()
    ):
        raise ValueError("monthly path angle anchor must be in [0, 360)")
    expected_angles = np.mod(
        np.degrees(
            np.arctan2(
                paths["quadrature"].to_numpy(dtype="float64"),
                paths["level"].to_numpy(dtype="float64"),
            )
        ),
        360.0,
    )
    if not np.allclose(
        paths["angle_degrees"],
        expected_angles,
        atol=1e-10,
        rtol=1e-10,
    ):
        raise ValueError("monthly path angle_degrees must align with level/quadrature")
    wrap_error = (
        paths["angle_unwrapped_degrees"].to_numpy(dtype="float64")
        - paths["angle_degrees"].to_numpy(dtype="float64")
        + 180.0
    ) % 360.0 - 180.0
    if not np.allclose(wrap_error, 0.0, atol=1e-10, rtol=1e-10):
        raise ValueError("monthly path unwrapped angles must preserve wrapped angles")
    expected_phases = _phase_labels(
        paths["level"].to_numpy(dtype="float64"),
        paths["slope"].to_numpy(dtype="float64"),
    )
    if not np.array_equal(paths["phase"].to_numpy(dtype=object), expected_phases):
        raise ValueError("monthly path phase must align with level and slope")
    expected_phase_transitions = paths["phase"].ne(paths["origin_phase"])
    if not paths["is_phase_transition"].equals(expected_phase_transitions):
        raise ValueError("monthly path phase transition flags are inconsistent")
    expected_slope_turns = paths["slope"].ge(0.0).ne(paths["origin_slope"].ge(0.0))
    if not paths["is_slope_turn"].equals(expected_slope_turns):
        raise ValueError("monthly path slope turn flags are inconsistent")
    events = paths["is_phase_transition"] | paths["is_slope_turn"]
    event_counts = events.groupby(
        [paths["cycle_id"], paths["draw_id"]],
        sort=False,
    ).cumsum()
    expected_first_turns = events & event_counts.eq(1)
    if not paths["is_first_turn"].equals(expected_first_turns):
        raise ValueError("monthly path first-turn flags are inconsistent")

    angle_steps = paths.groupby(
        ["cycle_id", "draw_id"],
        sort=False,
    )["angle_unwrapped_degrees"].diff()
    if bool(angle_steps.abs().dropna().gt(180.0 + 1e-10).any()):
        raise ValueError("monthly path unwrapped angles are not continuous")
    if bool(paths["analytic_uncertainty"].lt(0.0).any()):
        raise ValueError("monthly path analytic uncertainty must be nonnegative")
    if bool(paths["base_phase_velocity"].le(0.0).any()) or bool(
        paths["effective_phase_velocity"].le(0.0).any()
    ):
        raise ValueError("monthly path phase velocities must be positive")

    states = object.__getattribute__(forecast_input, "states")
    cycle_specs = object.__getattribute__(forecast_input, "cycle_specs")
    leading_signals = object.__getattribute__(forecast_input, "leading_signals")
    expected_config_hash = _config_hash(config)
    expected_registry_hash = _registry_hash(forecast_input)
    if set(paths["model_role"]) != {"champion"}:
        raise ValueError("monthly path model_role must be champion")
    if set(paths["forecast_model_version"]) != {config.model_version}:
        raise ValueError("monthly path forecast model version is inconsistent")
    if set(paths["forecast_config_hash"]) != {expected_config_hash}:
        raise ValueError("monthly path forecast config provenance is inconsistent")
    if set(paths["registry_hash"]) != {expected_registry_hash}:
        raise ValueError("monthly path registry provenance is inconsistent")

    for cycle in cycle_specs:
        cycle_paths = paths.loc[paths["cycle_id"].eq(cycle.cycle_id)]
        if cycle_paths.empty:
            continue
        state = states.loc[states["cycle_id"].eq(cycle.cycle_id)].iloc[0]
        signals = leading_signals.loc[leading_signals["cycle_id"].eq(cycle.cycle_id)]
        adjustments = _cycle_adjustments(state, cycle, signals, config)
        expected_anchor = float(
            np.mod(
                np.degrees(np.arctan2(state["quadrature"], state["level"])),
                360.0,
            )
        )
        if not np.allclose(
            cycle_paths["angle_anchor_degrees"],
            expected_anchor,
            atol=1e-10,
            rtol=1e-10,
        ):
            raise ValueError("monthly path angle anchor is inconsistent with state")
        for column, expected in (
            ("base_phase_velocity", adjustments["base_velocity"]),
            ("phase_velocity_adjustment", adjustments["velocity_adjustment"]),
            ("acceleration_adjustment", adjustments["acceleration_adjustment"]),
            ("duration_adjustment", adjustments["duration_adjustment"]),
            ("leading_adjustment", adjustments["leading_adjustment"]),
        ):
            if not np.allclose(
                cycle_paths[column],
                expected,
                atol=1e-10,
                rtol=1e-10,
            ):
                raise ValueError(f"monthly path {column} is inconsistent")
        if bool(
            cycle_paths["effective_phase_velocity"]
            .lt(0.4 * adjustments["base_velocity"] - 1e-12)
            .any()
        ) or bool(
            cycle_paths["effective_phase_velocity"]
            .gt(1.6 * adjustments["base_velocity"] + 1e-12)
            .any()
        ):
            raise ValueError("monthly path effective phase velocity is unbounded")
        if set(cycle_paths["state_model_version"]) != {state["state_model_version"]}:
            raise ValueError("monthly path state model provenance is inconsistent")
        if set(cycle_paths["state_config_hash"]) != {state["state_config_hash"]}:
            raise ValueError("monthly path state config provenance is inconsistent")
        if set(cycle_paths["data_vintage"]) != {state["data_vintage"]}:
            raise ValueError("monthly path data vintage provenance is inconsistent")
        uncertainty = (
            cycle_paths.groupby("month_number", sort=True)["analytic_uncertainty"]
            .agg(["min", "max"])
            .reset_index(drop=True)
        )
        if not np.allclose(
            uncertainty["min"],
            uncertainty["max"],
            atol=1e-12,
            rtol=1e-12,
        ):
            raise ValueError("monthly path uncertainty must be constant within month")
        if bool(uncertainty["min"].diff().dropna().lt(-1e-12).any()):
            raise ValueError("monthly path uncertainty cannot decline with horizon")


def _normalize_monthly_paths(
    values: object,
    *,
    forecast_input: CycleForecastInput,
    config: CycleForecastConfig,
) -> pd.DataFrame:
    paths = _required_frame(
        values,
        name="monthly_paths",
        columns=CYCLE_MONTHLY_PATH_COLUMNS,
    )
    paths["forecast_origin"] = _normalize_dates(
        paths["forecast_origin"],
        name="monthly path forecast_origin",
    )
    paths["date"] = _normalize_dates(paths["date"], name="monthly path date")
    paths["data_vintage"] = _normalize_dates(
        paths["data_vintage"],
        name="monthly path data_vintage",
    )
    as_of = pd.Timestamp(forecast_input.as_of)
    if set(paths["forecast_origin"]) != ({as_of} if not paths.empty else set()):
        raise ValueError("monthly path forecast_origin must equal input as_of")
    if not paths.empty and bool((paths["data_vintage"] > as_of).any()):
        raise ValueError("monthly path data_vintage cannot follow as_of")
    normalized_draw_ids = [
        _nonnegative_integer(value, name="monthly path draw_id")
        for value in paths["draw_id"].tolist()
    ]
    normalized_months = [
        _positive_integer(value, name="monthly path month_number")
        for value in paths["month_number"].tolist()
    ]
    paths["draw_id"] = pd.Series(
        normalized_draw_ids,
        index=paths.index,
        dtype="int64",
    )
    paths["month_number"] = pd.Series(
        normalized_months,
        index=paths.index,
        dtype="int64",
    )
    expected_dates = pd.Series(
        [_forecast_date(as_of, month_number) for month_number in normalized_months],
        index=paths.index,
        dtype="datetime64[ns]",
    )
    if not paths["date"].equals(expected_dates):
        raise ValueError(
            "monthly path date must match forecast_origin and month_number"
        )
    states = object.__getattribute__(forecast_input, "states")
    cycle_specs = object.__getattribute__(forecast_input, "cycle_specs")
    available_cycles = set(states.loc[states["status"].eq("available"), "cycle_id"])
    if set(paths["cycle_id"]) != available_cycles:
        raise ValueError("monthly paths must cover exactly the available cycles")
    if paths.duplicated(["cycle_id", "draw_id", "month_number"]).any():
        raise ValueError("monthly path dimensions must be unique")
    paths = paths.sort_values(
        ["cycle_id", "draw_id", "month_number"],
        kind="stable",
    ).reset_index(drop=True)
    _validate_path_geometry(
        paths,
        forecast_input=forecast_input,
        config=config,
    )
    expected_draw_ids = set(range(config.draw_count))
    for cycle in cycle_specs:
        if cycle.cycle_id not in available_cycles:
            continue
        cycle_paths = paths.loc[paths["cycle_id"].eq(cycle.cycle_id)]
        if set(cycle_paths["draw_id"]) != expected_draw_ids:
            raise ValueError("monthly path draw_id coverage is incomplete")
        expected_months = set(range(1, max(cycle.horizons) + 1))
        if set(cycle_paths["month_number"]) != expected_months:
            raise ValueError("monthly paths must cover the longest registry horizon")
        if len(cycle_paths) != config.draw_count * len(expected_months):
            raise ValueError("monthly paths must retain one shared path per draw")
    return paths


def _generate_monthly_paths(
    forecast_input: CycleForecastInput,
    config: CycleForecastConfig,
) -> pd.DataFrame:
    states = object.__getattribute__(forecast_input, "states")
    cycle_specs = object.__getattribute__(forecast_input, "cycle_specs")
    leading_signals = object.__getattribute__(forecast_input, "leading_signals")
    as_of = pd.Timestamp(forecast_input.as_of)
    forecast_config_hash = _config_hash(config)
    registry_hash = _registry_hash(forecast_input)
    path_records: list[dict[str, object]] = []
    for cycle in cycle_specs:
        state = states.loc[states["cycle_id"].eq(cycle.cycle_id)].iloc[0]
        if state["status"] == "unavailable":
            continue
        signals = leading_signals.loc[leading_signals["cycle_id"].eq(cycle.cycle_id)]
        path_records.extend(
            _simulate_cycle_paths(
                state=state,
                cycle=cycle,
                signals=signals,
                as_of=as_of,
                config=config,
                forecast_config_hash=forecast_config_hash,
                registry_hash=registry_hash,
            )
        )
    return (
        pd.DataFrame(path_records, columns=CYCLE_MONTHLY_PATH_COLUMNS)
        .sort_values(
            ["cycle_id", "draw_id", "month_number"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


@dataclass(frozen=True)
class CycleForecastResult:
    """Detached shared monthly paths and summaries rebuilt against retained inputs."""

    summary: pd.DataFrame
    monthly_paths: pd.DataFrame
    forecast_input: CycleForecastInput
    config: CycleForecastConfig

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_input, CycleForecastInput):
            raise TypeError("forecast_input must be a CycleForecastInput")
        if not isinstance(self.config, CycleForecastConfig):
            raise TypeError("config must be a CycleForecastConfig")
        paths = _normalize_monthly_paths(
            object.__getattribute__(self, "monthly_paths"),
            forecast_input=self.forecast_input,
            config=self.config,
        )
        expected_paths = _normalize_monthly_paths(
            _generate_monthly_paths(self.forecast_input, self.config),
            forecast_input=self.forecast_input,
            config=self.config,
        )
        try:
            pd.testing.assert_frame_equal(
                paths,
                expected_paths,
                check_dtype=True,
                check_exact=True,
            )
        except AssertionError as error:
            raise ValueError(
                "monthly paths are inconsistent with deterministic replay"
            ) from error
        supplied = (
            _required_frame(
                object.__getattribute__(self, "summary"),
                name="summary",
                columns=CYCLE_FORECAST_SUMMARY_COLUMNS,
            )
            .sort_values(["cycle_id", "horizon_months"], kind="stable")
            .reset_index(drop=True)
        )
        expected = (
            _build_summary(
                forecast_input=self.forecast_input,
                monthly_paths=paths,
                config=self.config,
            )
            .sort_values(["cycle_id", "horizon_months"], kind="stable")
            .reset_index(drop=True)
        )
        try:
            pd.testing.assert_frame_equal(
                supplied,
                expected,
                check_dtype=True,
                check_exact=True,
            )
        except AssertionError as error:
            raise ValueError(
                "summary is inconsistent with retained monthly paths"
            ) from error
        object.__setattr__(self, "summary", expected.copy(deep=True))
        object.__setattr__(self, "monthly_paths", paths.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.summary

    @property
    def retained_paths(self) -> pd.DataFrame:
        return self.monthly_paths


def forecast_cycle_phases(
    forecast_input: CycleForecastInput,
    *,
    config: CycleForecastConfig | None = None,
) -> CycleForecastResult:
    """Forecast C1-C7 phase distributions on each registry-defined horizon."""

    if not isinstance(forecast_input, CycleForecastInput):
        raise TypeError("forecast_input must be a CycleForecastInput")
    normalized_config = config or CycleForecastConfig()
    if not isinstance(normalized_config, CycleForecastConfig):
        raise TypeError("config must be a CycleForecastConfig")
    monthly_paths = _generate_monthly_paths(forecast_input, normalized_config)
    summary = _build_summary(
        forecast_input=forecast_input,
        monthly_paths=monthly_paths,
        config=normalized_config,
    )
    return CycleForecastResult(
        summary=summary,
        monthly_paths=monthly_paths,
        forecast_input=forecast_input,
        config=normalized_config,
    )


__all__ = [
    "CALIBRATION_HISTORY_COLUMNS",
    "CYCLE_FORECAST_SUMMARY_COLUMNS",
    "CYCLE_MONTHLY_PATH_COLUMNS",
    "CYCLE_STATE_COLUMNS",
    "LEADING_SIGNAL_COLUMNS",
    "CycleForecastConfig",
    "CycleForecastInput",
    "CycleForecastResult",
    "forecast_cycle_phases",
]
