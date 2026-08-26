"""Point-in-time transmission-channel forecasts with audited baselines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
from numbers import Integral, Real
from typing import Sequence

import numpy as np
import pandas as pd

from seven_cycle_platform.forecast.cycles import CycleForecastResult
from seven_cycle_platform.registry.models import ChannelSpec


CHANNEL_HISTORY_COLUMNS = (
    "forecast_origin",
    "origin_state_date",
    "origin_visible_date",
    "target_date",
    "target_visible_date",
    "target_revision_window_end",
    "channel_id",
    "horizon_months",
    "origin_state",
    "origin_innovation",
    "origin_uncertainty",
    "origin_status",
    "origin_status_reason",
    "target_state",
    "target_innovation",
    "target_uncertainty",
    "target_status",
    "target_status_reason",
    "data_vintage",
)
CYCLE_PREDICTOR_ARCHIVE_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "cycle_id",
    "draw_id",
    "horizon_months",
    "level",
    "slope",
    "predictor_kind",
    "forecast_model_version",
    "forecast_config_hash",
    "registry_hash",
    "data_vintage",
)
EXOGENOUS_FORECAST_ARCHIVE_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "feature_id",
    "draw_id",
    "horizon_months",
    "value",
    "is_deterministic",
    "path_kind",
)
CURRENT_CHANNEL_STATE_COLUMNS = (
    "as_of",
    "state_date",
    "visible_date",
    "revision_window_end",
    "channel_id",
    "state",
    "innovation",
    "uncertainty",
    "status",
    "status_reason",
    "data_vintage",
)
CURRENT_EXOGENOUS_PATH_COLUMNS = EXOGENOUS_FORECAST_ARCHIVE_COLUMNS
CHANNEL_FORECAST_SUMMARY_COLUMNS = (
    "as_of",
    "forecast_date",
    "channel_id",
    "horizon_months",
    "status",
    "unavailable_reason",
    "selected_model",
    "forecast_mean",
    "forecast_std",
    "innovation_mean",
    "q10",
    "q25",
    "q50",
    "q75",
    "q90",
    "probability_positive",
    "probability_negative",
    "origin_state",
    "origin_innovation",
    "origin_uncertainty",
    "active_cycle_count",
    "active_cycle_ids",
    "missing_cycle_ids",
    "support_uncertainty_multiplier",
    "feature_labels",
    "selected_alpha",
    "training_count",
    "training_end",
    "embargo_cutoff",
    "calibration_status",
    "evaluation_status",
    "evaluation_fold_count",
    "champion_oos_loss",
    "historical_mean_oos_loss",
    "persistence_oos_loss",
    "covariance_status",
    "covariance_method",
    "covariance_sample_count",
    "model_role",
    "forecast_model_version",
    "forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "data_vintage",
)
CHANNEL_FORECAST_DRAW_COLUMNS = (
    "as_of",
    "forecast_date",
    "channel_id",
    "draw_id",
    "cycle_draw_id",
    "horizon_months",
    "status",
    "unavailable_reason",
    "selected_model",
    "forecast_state",
    "forecast_innovation",
    "forecast_mean",
    "residual",
    "origin_state",
    "active_cycle_ids",
    "missing_cycle_ids",
    "feature_labels",
    "model_role",
    "forecast_model_version",
    "forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "data_vintage",
)
CHANNEL_FORECAST_COVARIANCE_COLUMNS = (
    "as_of",
    "forecast_date",
    "horizon_months",
    "channel_i",
    "channel_j",
    "covariance",
    "correlation",
    "sample_count",
    "method",
    "status",
    "fallback_reason",
    "support_uncertainty_multiplier",
    "forecast_model_version",
    "forecast_config_hash",
    "channel_registry_hash",
    "data_vintage",
)
CHANNEL_FORECAST_EVALUATION_COLUMNS = (
    "fold_id",
    "validation_origin",
    "target_date",
    "channel_id",
    "horizon_months",
    "status",
    "reason",
    "realized_state",
    "champion_prediction",
    "historical_mean_prediction",
    "persistence_prediction",
    "champion_loss",
    "historical_mean_loss",
    "persistence_loss",
    "selected_model",
    "selected_alpha",
    "alpha_validation_count",
    "training_count",
    "training_end",
    "embargo_cutoff",
    "feature_labels",
    "active_cycle_ids",
    "missing_cycle_ids",
    "forecast_model_version",
    "forecast_config_hash",
    "channel_registry_hash",
)

_INPUT_FRAME_FIELDS = frozenset(
    {
        "channel_history",
        "cycle_predictor_archive",
        "exogenous_forecast_archive",
        "current_channel_states",
        "current_exogenous_paths",
    }
)
_RESULT_FRAME_FIELDS = frozenset({"summary", "draws", "covariance", "evaluation"})
_RESULT_SPECS = {
    "summary": (
        CHANNEL_FORECAST_SUMMARY_COLUMNS,
        ["channel_id", "horizon_months"],
    ),
    "draws": (
        CHANNEL_FORECAST_DRAW_COLUMNS,
        ["channel_id", "horizon_months", "draw_id"],
    ),
    "covariance": (
        CHANNEL_FORECAST_COVARIANCE_COLUMNS,
        ["horizon_months", "channel_i", "channel_j"],
    ),
    "evaluation": (
        CHANNEL_FORECAST_EVALUATION_COLUMNS,
        ["channel_id", "horizon_months", "validation_origin"],
    ),
}


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


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


def _nonnegative_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _positive_real(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if numeric <= 0.0:
        raise ValueError(f"{name} must be positive")
    return numeric


def _bounded_fraction(value: object, *, name: str) -> float:
    numeric = _finite_real(value, name=name)
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return numeric


def _normalize_text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty")
    return normalized


def _normalize_optional_text(value: object, *, name: str) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return _normalize_text(value, name=name)


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
        raise ValueError(f"{name} columns do not match the channel forecast contract")
    return values.copy(deep=True)


def _forecast_date(origin: pd.Timestamp, horizon: int) -> pd.Timestamp:
    return origin + pd.offsets.MonthEnd(horizon)


def _stable_hash(payload: object) -> str:
    serialized = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_hash(value: object, *, name: str) -> str:
    normalized = _normalize_text(value, name=name)
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return normalized


def _normalize_channel_specs(values: object) -> tuple[ChannelSpec, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("channel_specs must be a sequence of ChannelSpec objects")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "channel_specs must be a sequence of ChannelSpec objects"
        ) from error
    if not supplied:
        raise ValueError("channel_specs cannot be empty")
    if any(not isinstance(channel, ChannelSpec) for channel in supplied):
        raise TypeError("channel_specs must contain only ChannelSpec objects")
    channel_ids = [channel.channel_id for channel in supplied]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("channel_specs contain duplicate channel_id values")
    return tuple(
        channel.model_copy(deep=True)
        for channel in sorted(supplied, key=lambda item: item.channel_id)
    )


def _normalize_feature_ids(values: object) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError("exogenous_feature_ids must be a sequence of strings")
    try:
        supplied = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise TypeError(
            "exogenous_feature_ids must be a sequence of strings"
        ) from error
    normalized = tuple(
        _normalize_text(value, name="exogenous feature_id") for value in supplied
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError("exogenous_feature_ids must be unique")
    return tuple(sorted(normalized))


def _rebuild_cycle_forecast(value: object) -> CycleForecastResult:
    if not isinstance(value, CycleForecastResult):
        raise TypeError("cycle_forecast must be a CycleForecastResult")
    try:
        return CycleForecastResult(
            summary=value.summary,
            monthly_paths=value.monthly_paths,
            forecast_input=value.forecast_input,
            config=value.config,
        )
    except ValueError as error:
        raise ValueError(
            "cycle forecast is inconsistent with deterministic replay"
        ) from error


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_status_row(
    row: dict[str, object],
    *,
    prefix: str,
    status_column: str,
    reason_column: str,
    numeric_columns: tuple[str, ...],
    uncertainty_column: str,
) -> None:
    status = _normalize_text(row[status_column], name=f"{prefix} status")
    if status not in {"available", "unavailable"}:
        raise ValueError(f"{prefix} status must be available or unavailable")
    reason = _normalize_optional_text(
        row[reason_column],
        name=f"{prefix} status reason",
    )
    if status == "available":
        if reason is not None:
            raise ValueError(f"available {prefix} rows cannot define a reason")
        for column in numeric_columns:
            row[column] = _finite_real(row[column], name=f"{prefix} {column}")
        row[uncertainty_column] = _nonnegative_real(
            row[uncertainty_column],
            name=f"{prefix} {uncertainty_column}",
        )
    else:
        if reason is None:
            raise ValueError(f"unavailable {prefix} rows require a reason")
        if any(not _is_missing(row[column]) for column in numeric_columns):
            raise ValueError(f"unavailable {prefix} numeric values must be missing")
    row[status_column] = status
    row[reason_column] = reason


def _normalize_channel_history(
    values: object,
    *,
    as_of: pd.Timestamp,
    channel_specs: tuple[ChannelSpec, ...],
) -> pd.DataFrame:
    history = _required_frame(
        values,
        name="channel_history",
        columns=CHANNEL_HISTORY_COLUMNS,
    )
    for column in (
        "forecast_origin",
        "origin_state_date",
        "origin_visible_date",
        "target_date",
        "target_visible_date",
        "target_revision_window_end",
        "data_vintage",
    ):
        history[column] = _normalize_dates(
            history[column],
            name=f"channel_history {column}",
        )
    if bool((history["forecast_origin"] >= as_of).any()):
        raise ValueError("historical forecast_origin must be strictly before as_of")
    if bool((history["origin_state_date"] > history["origin_visible_date"]).any()):
        raise ValueError("origin_state_date cannot follow origin_visible_date")
    if bool((history["origin_visible_date"] > history["forecast_origin"]).any()):
        raise ValueError("origin channel state must be visible by forecast_origin")
    if bool((history["forecast_origin"] >= history["target_date"]).any()):
        raise ValueError("historical forecast_origin must precede target_date")
    if bool((history["target_date"] > history["target_visible_date"]).any()):
        raise ValueError("target_date cannot follow target_visible_date")
    if bool(
        (history["target_visible_date"] > history["target_revision_window_end"]).any()
    ):
        raise ValueError("target_visible_date cannot follow target_revision_window_end")
    if bool((history["data_vintage"] < history["target_visible_date"]).any()):
        raise ValueError("data_vintage cannot precede target_visible_date")
    if bool((history["data_vintage"] > history["target_revision_window_end"]).any()):
        raise ValueError("data_vintage cannot follow target_revision_window_end")
    if bool((history["data_vintage"] > as_of).any()):
        raise ValueError("data_vintage cannot follow as_of")
    channel_ids = {channel.channel_id for channel in channel_specs}
    if not set(history["channel_id"]).issubset(channel_ids):
        raise ValueError("channel_history channel coverage is not registered")
    normalized_rows = []
    for raw_row in history.to_dict(orient="records"):
        row = dict(raw_row)
        channel_id = row["channel_id"]
        if not isinstance(channel_id, str):
            raise TypeError("channel_history channel_id values must be strings")
        horizon = _positive_integer(
            row["horizon_months"],
            name="channel_history horizon_months",
        )
        if row["target_date"] != _forecast_date(row["forecast_origin"], horizon):
            raise ValueError(
                "channel_history target_date must match forecast_origin and horizon"
            )
        row["horizon_months"] = horizon
        _normalize_status_row(
            row,
            prefix="origin channel",
            status_column="origin_status",
            reason_column="origin_status_reason",
            numeric_columns=(
                "origin_state",
                "origin_innovation",
                "origin_uncertainty",
            ),
            uncertainty_column="origin_uncertainty",
        )
        _normalize_status_row(
            row,
            prefix="target channel",
            status_column="target_status",
            reason_column="target_status_reason",
            numeric_columns=(
                "target_state",
                "target_innovation",
                "target_uncertainty",
            ),
            uncertainty_column="target_uncertainty",
        )
        normalized_rows.append(row)
    history = pd.DataFrame(normalized_rows, columns=CHANNEL_HISTORY_COLUMNS)
    if history.duplicated(["forecast_origin", "channel_id", "horizon_months"]).any():
        raise ValueError("channel_history contains duplicate forecast folds")
    for _, group in history.groupby(
        ["forecast_origin", "horizon_months"],
        sort=False,
    ):
        if set(group["channel_id"]) != channel_ids or len(group) != len(channel_ids):
            raise ValueError(
                "channel_history channel coverage must exactly match channel_specs"
            )
    return history.sort_values(
        ["forecast_origin", "horizon_months", "channel_id"],
        kind="stable",
    ).reset_index(drop=True)


def _cycle_specs(cycle_forecast: CycleForecastResult):
    forecast_input = object.__getattribute__(cycle_forecast, "forecast_input")
    return object.__getattribute__(forecast_input, "cycle_specs")


def _normalize_cycle_archive(
    values: object,
    *,
    as_of: pd.Timestamp,
    cycle_forecast: CycleForecastResult,
) -> pd.DataFrame:
    archive = _required_frame(
        values,
        name="cycle_predictor_archive",
        columns=CYCLE_PREDICTOR_ARCHIVE_COLUMNS,
    )
    for column in (
        "forecast_origin",
        "date",
        "visible_date",
        "generated_date",
        "data_vintage",
    ):
        archive[column] = _normalize_dates(
            archive[column],
            name=f"cycle_predictor_archive {column}",
        )
    if archive.empty:
        return archive.reset_index(drop=True)
    if bool((archive["forecast_origin"] >= as_of).any()):
        raise ValueError("historical cycle forecast_origin must precede as_of")
    if bool((archive["forecast_origin"] >= archive["date"]).any()):
        raise ValueError("historical cycle forecast_origin must precede target date")
    if bool((archive["visible_date"] > archive["forecast_origin"]).any()):
        raise ValueError("historical cycle predictors must be visible by their origin")
    if bool((archive["generated_date"] > archive["forecast_origin"]).any()):
        raise ValueError(
            "historical cycle predictors must be generated by their origin"
        )
    if bool((archive["data_vintage"] > archive["forecast_origin"]).any()):
        raise ValueError("historical cycle predictor vintage cannot follow its origin")
    specifications = {cycle.cycle_id: cycle for cycle in _cycle_specs(cycle_forecast)}
    normalized_rows = []
    for raw_row in archive.to_dict(orient="records"):
        row = dict(raw_row)
        cycle_id = row["cycle_id"]
        if not isinstance(cycle_id, str) or cycle_id not in specifications:
            raise ValueError("cycle_predictor_archive cycle_id is not registered")
        if row["predictor_kind"] != "forecast":
            raise ValueError(
                "cycle_predictor_archive must contain forecast predictors only"
            )
        horizon = _positive_integer(
            row["horizon_months"],
            name="cycle predictor horizon_months",
        )
        if horizon > max(specifications[cycle_id].horizons):
            raise ValueError("cycle predictor horizon exceeds approved cycle support")
        if row["date"] != _forecast_date(row["forecast_origin"], horizon):
            raise ValueError(
                "cycle predictor date must match forecast_origin and horizon"
            )
        row["horizon_months"] = horizon
        row["draw_id"] = _nonnegative_integer(
            row["draw_id"],
            name="cycle predictor draw_id",
        )
        row["level"] = _finite_real(row["level"], name="cycle predictor level")
        row["slope"] = _finite_real(row["slope"], name="cycle predictor slope")
        row["forecast_model_version"] = _normalize_text(
            row["forecast_model_version"],
            name="cycle predictor forecast_model_version",
        )
        row["forecast_config_hash"] = _validate_hash(
            row["forecast_config_hash"],
            name="cycle predictor forecast_config_hash",
        )
        row["registry_hash"] = _validate_hash(
            row["registry_hash"],
            name="cycle predictor registry_hash",
        )
        normalized_rows.append(row)
    archive = pd.DataFrame(normalized_rows, columns=CYCLE_PREDICTOR_ARCHIVE_COLUMNS)
    if archive.duplicated(
        ["forecast_origin", "cycle_id", "horizon_months", "draw_id"]
    ).any():
        raise ValueError("cycle_predictor_archive contains duplicate draw rows")
    for _, group in archive.groupby(
        ["forecast_origin", "cycle_id", "horizon_months"],
        sort=False,
    ):
        expected = set(range(int(group["draw_id"].max()) + 1))
        if set(group["draw_id"]) != expected:
            raise ValueError(
                "historical cycle predictor draw_id coverage is incomplete"
            )
    return archive.sort_values(
        ["forecast_origin", "horizon_months", "cycle_id", "draw_id"],
        kind="stable",
    ).reset_index(drop=True)


def _normalize_boolean(value: object, *, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a boolean")
    return bool(value)


def _normalize_exogenous_archive(
    values: object,
    *,
    as_of: pd.Timestamp,
    feature_ids: tuple[str, ...],
) -> pd.DataFrame:
    archive = _required_frame(
        values,
        name="exogenous_forecast_archive",
        columns=EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
    )
    for column in ("forecast_origin", "date", "visible_date", "generated_date"):
        archive[column] = _normalize_dates(
            archive[column],
            name=f"exogenous_forecast_archive {column}",
        )
    if archive.empty:
        return archive.reset_index(drop=True)
    if not feature_ids:
        raise ValueError(
            "exogenous_forecast_archive must be empty without approved features"
        )
    if bool((archive["forecast_origin"] >= as_of).any()):
        raise ValueError("historical exogenous forecast_origin must precede as_of")
    if bool((archive["forecast_origin"] >= archive["date"]).any()):
        raise ValueError(
            "historical exogenous forecast_origin must precede target date"
        )
    if bool((archive["visible_date"] > archive["forecast_origin"]).any()):
        raise ValueError("historical exogenous forecasts must be visible by origin")
    if bool((archive["generated_date"] > archive["forecast_origin"]).any()):
        raise ValueError("historical exogenous forecasts must be generated by origin")
    normalized_rows = []
    for raw_row in archive.to_dict(orient="records"):
        row = dict(raw_row)
        feature_id = row["feature_id"]
        if not isinstance(feature_id, str) or feature_id not in feature_ids:
            raise ValueError("exogenous forecast feature_id is not approved")
        if row["path_kind"] != "forecast":
            raise ValueError("historical exogenous paths must be forecast paths only")
        horizon = _positive_integer(
            row["horizon_months"],
            name="exogenous forecast horizon_months",
        )
        if row["date"] != _forecast_date(row["forecast_origin"], horizon):
            raise ValueError(
                "exogenous forecast date must match forecast_origin and horizon"
            )
        row["horizon_months"] = horizon
        row["draw_id"] = _nonnegative_integer(
            row["draw_id"],
            name="exogenous forecast draw_id",
        )
        row["value"] = _finite_real(
            row["value"],
            name="exogenous forecast value",
        )
        row["is_deterministic"] = _normalize_boolean(
            row["is_deterministic"],
            name="exogenous forecast is_deterministic",
        )
        normalized_rows.append(row)
    archive = pd.DataFrame(
        normalized_rows,
        columns=EXOGENOUS_FORECAST_ARCHIVE_COLUMNS,
    )
    if archive.duplicated(
        ["forecast_origin", "feature_id", "horizon_months", "draw_id"]
    ).any():
        raise ValueError("exogenous_forecast_archive contains duplicate draw rows")
    _validate_exogenous_groups(archive, expected_draw_ids=None, historical=True)
    return archive.sort_values(
        ["forecast_origin", "horizon_months", "feature_id", "draw_id"],
        kind="stable",
    ).reset_index(drop=True)


def _validate_exogenous_groups(
    values: pd.DataFrame,
    *,
    expected_draw_ids: set[int] | None,
    historical: bool,
) -> None:
    grouping = ["forecast_origin", "feature_id", "horizon_months"]
    for _, group in values.groupby(grouping, sort=False):
        flags = set(group["is_deterministic"])
        if len(flags) != 1:
            raise ValueError("exogenous draw groups cannot mix deterministic modes")
        deterministic = bool(next(iter(flags)))
        if deterministic:
            if len(group) != 1 or set(group["draw_id"]) != {0}:
                raise ValueError(
                    "deterministic exogenous paths require one draw_id zero row"
                )
            continue
        if historical:
            expected = set(range(int(group["draw_id"].max()) + 1))
        else:
            expected = expected_draw_ids or set()
        if set(group["draw_id"]) != expected:
            raise ValueError("exogenous draw_id coverage is incomplete")


def _normalize_current_states(
    values: object,
    *,
    as_of: pd.Timestamp,
    channel_specs: tuple[ChannelSpec, ...],
) -> pd.DataFrame:
    states = _required_frame(
        values,
        name="current_channel_states",
        columns=CURRENT_CHANNEL_STATE_COLUMNS,
    )
    for column in (
        "as_of",
        "state_date",
        "visible_date",
        "revision_window_end",
        "data_vintage",
    ):
        states[column] = _normalize_dates(
            states[column],
            name=f"current_channel_states {column}",
        )
    if set(states["as_of"]) != {as_of}:
        raise ValueError("current channel state as_of must match forecast as_of")
    if bool((states["state_date"] > states["visible_date"]).any()):
        raise ValueError("current channel state_date cannot follow visible_date")
    if bool((states["visible_date"] > as_of).any()):
        raise ValueError("future-visible current channel states are not allowed")
    if bool((states["revision_window_end"] < states["visible_date"]).any()):
        raise ValueError("current revision_window_end cannot precede visible_date")
    if bool((states["data_vintage"] > as_of).any()):
        raise ValueError("current channel data_vintage cannot follow as_of")
    channel_ids = {channel.channel_id for channel in channel_specs}
    if set(states["channel_id"]) != channel_ids or len(states) != len(channel_ids):
        raise ValueError(
            "current channel state coverage must exactly match channel_specs"
        )
    normalized_rows = []
    for raw_row in states.to_dict(orient="records"):
        row = dict(raw_row)
        _normalize_status_row(
            row,
            prefix="current channel",
            status_column="status",
            reason_column="status_reason",
            numeric_columns=("state", "innovation", "uncertainty"),
            uncertainty_column="uncertainty",
        )
        normalized_rows.append(row)
    states = pd.DataFrame(normalized_rows, columns=CURRENT_CHANNEL_STATE_COLUMNS)
    if states.duplicated("channel_id").any():
        raise ValueError("current_channel_states contain duplicate channel rows")
    return states.sort_values("channel_id", kind="stable").reset_index(drop=True)


def _normalize_current_exogenous_paths(
    values: object,
    *,
    as_of: pd.Timestamp,
    feature_ids: tuple[str, ...],
    cycle_forecast: CycleForecastResult,
) -> pd.DataFrame:
    paths = _required_frame(
        values,
        name="current_exogenous_paths",
        columns=CURRENT_EXOGENOUS_PATH_COLUMNS,
    )
    for column in ("forecast_origin", "date", "visible_date", "generated_date"):
        paths[column] = _normalize_dates(
            paths[column],
            name=f"current_exogenous_paths {column}",
        )
    if not feature_ids:
        if not paths.empty:
            raise ValueError(
                "current_exogenous_paths must be empty without approved features"
            )
        return paths.reset_index(drop=True)
    if paths.empty:
        raise ValueError("current_exogenous_paths require approved feature coverage")
    if set(paths["forecast_origin"]) != {as_of}:
        raise ValueError("current exogenous forecast_origin must equal as_of")
    if bool((paths["date"] <= as_of).any()):
        raise ValueError("current exogenous paths must target future dates")
    if bool((paths["visible_date"] > as_of).any()):
        raise ValueError("current exogenous paths must be visible by as_of")
    if bool((paths["generated_date"] > as_of).any()):
        raise ValueError("current exogenous paths must be generated by as_of")
    normalized_rows = []
    for raw_row in paths.to_dict(orient="records"):
        row = dict(raw_row)
        feature_id = row["feature_id"]
        if not isinstance(feature_id, str) or feature_id not in feature_ids:
            raise ValueError("current exogenous feature_id is not approved")
        if row["path_kind"] != "forecast":
            raise ValueError("current exogenous paths must be forecast paths only")
        horizon = _positive_integer(
            row["horizon_months"],
            name="current exogenous horizon_months",
        )
        if row["date"] != _forecast_date(as_of, horizon):
            raise ValueError(
                "current exogenous date must match forecast_origin and horizon"
            )
        row["horizon_months"] = horizon
        row["draw_id"] = _nonnegative_integer(
            row["draw_id"],
            name="current exogenous draw_id",
        )
        row["value"] = _finite_real(
            row["value"],
            name="current exogenous value",
        )
        row["is_deterministic"] = _normalize_boolean(
            row["is_deterministic"],
            name="current exogenous is_deterministic",
        )
        normalized_rows.append(row)
    paths = pd.DataFrame(normalized_rows, columns=CURRENT_EXOGENOUS_PATH_COLUMNS)
    if paths.duplicated(["feature_id", "horizon_months", "draw_id"]).any():
        raise ValueError("current_exogenous_paths contain duplicate draw rows")
    for _, group in paths.groupby("horizon_months", sort=False):
        if set(group["feature_id"]) != set(feature_ids):
            raise ValueError(
                "current exogenous feature coverage must be exact by horizon"
            )
    expected_draw_ids = set(range(cycle_forecast.config.draw_count))
    _validate_exogenous_groups(
        paths,
        expected_draw_ids=expected_draw_ids,
        historical=False,
    )
    return paths.sort_values(
        ["horizon_months", "feature_id", "draw_id"],
        kind="stable",
    ).reset_index(drop=True)


@dataclass(frozen=True)
class ChannelForecastConfig:
    """Immutable direct-horizon ARX, embargo, and covariance configuration."""

    horizons: tuple[int, ...] = tuple(range(1, 13))
    alpha_grid: tuple[float, ...] = (0.05, 0.5, 5.0)
    min_training_count: int = 12
    alpha_validation_window: int = 6
    embargo_days: int = 0
    covariance_min_samples: int = 6
    covariance_shrinkage: float = 0.20
    fallback_variance_floor: float = 1e-6
    seed: int = 0
    model_version: str = "channel-champion-v1"

    def __post_init__(self) -> None:
        horizons = tuple(
            sorted(
                {_positive_integer(value, name="horizon") for value in self.horizons}
            )
        )
        if not horizons:
            raise ValueError("horizons cannot be empty")
        alphas = tuple(
            sorted(
                {_nonnegative_real(value, name="alpha") for value in self.alpha_grid}
            )
        )
        if not alphas:
            raise ValueError("alpha_grid cannot be empty")
        object.__setattr__(self, "horizons", horizons)
        object.__setattr__(self, "alpha_grid", alphas)
        object.__setattr__(
            self,
            "min_training_count",
            _positive_integer(
                self.min_training_count,
                name="min_training_count",
            ),
        )
        object.__setattr__(
            self,
            "alpha_validation_window",
            _positive_integer(
                self.alpha_validation_window,
                name="alpha_validation_window",
            ),
        )
        object.__setattr__(
            self,
            "embargo_days",
            _nonnegative_integer(self.embargo_days, name="embargo_days"),
        )
        object.__setattr__(
            self,
            "covariance_min_samples",
            _positive_integer(
                self.covariance_min_samples,
                name="covariance_min_samples",
            ),
        )
        object.__setattr__(
            self,
            "covariance_shrinkage",
            _bounded_fraction(
                self.covariance_shrinkage,
                name="covariance_shrinkage",
            ),
        )
        object.__setattr__(
            self,
            "fallback_variance_floor",
            _positive_real(
                self.fallback_variance_floor,
                name="fallback_variance_floor",
            ),
        )
        object.__setattr__(
            self,
            "seed",
            _nonnegative_integer(self.seed, name="seed"),
        )
        object.__setattr__(
            self,
            "model_version",
            _normalize_text(self.model_version, name="model_version"),
        )


@dataclass(frozen=True)
class ChannelForecastInput:
    """Explicit point-in-time archives and current channel forecast inputs."""

    as_of: date
    channel_specs: Sequence[ChannelSpec]
    cycle_forecast: CycleForecastResult
    channel_history: pd.DataFrame
    cycle_predictor_archive: pd.DataFrame
    exogenous_forecast_archive: pd.DataFrame
    current_channel_states: pd.DataFrame
    current_exogenous_paths: pd.DataFrame
    exogenous_feature_ids: Sequence[str]

    def __post_init__(self) -> None:
        as_of = _normalize_date(self.as_of, name="as_of")
        channel_specs = _normalize_channel_specs(
            object.__getattribute__(self, "channel_specs")
        )
        cycle_forecast = _rebuild_cycle_forecast(
            object.__getattribute__(self, "cycle_forecast")
        )
        if pd.Timestamp(cycle_forecast.forecast_input.as_of) != as_of:
            raise ValueError("cycle forecast as_of must equal channel forecast as_of")
        if cycle_forecast.config.draw_count < 2:
            raise ValueError("cycle_forecast must retain at least 2 draws")
        feature_ids = _normalize_feature_ids(
            object.__getattribute__(self, "exogenous_feature_ids")
        )
        channel_history = _normalize_channel_history(
            object.__getattribute__(self, "channel_history"),
            as_of=as_of,
            channel_specs=channel_specs,
        )
        cycle_archive = _normalize_cycle_archive(
            object.__getattribute__(self, "cycle_predictor_archive"),
            as_of=as_of,
            cycle_forecast=cycle_forecast,
        )
        exogenous_archive = _normalize_exogenous_archive(
            object.__getattribute__(self, "exogenous_forecast_archive"),
            as_of=as_of,
            feature_ids=feature_ids,
        )
        current_states = _normalize_current_states(
            object.__getattribute__(self, "current_channel_states"),
            as_of=as_of,
            channel_specs=channel_specs,
        )
        current_exogenous = _normalize_current_exogenous_paths(
            object.__getattribute__(self, "current_exogenous_paths"),
            as_of=as_of,
            feature_ids=feature_ids,
            cycle_forecast=cycle_forecast,
        )
        object.__setattr__(self, "as_of", as_of.date())
        object.__setattr__(self, "channel_specs", channel_specs)
        object.__setattr__(self, "cycle_forecast", cycle_forecast)
        object.__setattr__(self, "channel_history", channel_history)
        object.__setattr__(self, "cycle_predictor_archive", cycle_archive)
        object.__setattr__(self, "exogenous_forecast_archive", exogenous_archive)
        object.__setattr__(self, "current_channel_states", current_states)
        object.__setattr__(self, "current_exogenous_paths", current_exogenous)
        object.__setattr__(self, "exogenous_feature_ids", feature_ids)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _INPUT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        if name == "channel_specs" and isinstance(value, tuple):
            return tuple(channel.model_copy(deep=True) for channel in value)
        return value


@dataclass(frozen=True)
class _TrainingSample:
    forecast_origin: pd.Timestamp
    target_date: pd.Timestamp
    target_visible_date: pd.Timestamp
    target_revision_window_end: pd.Timestamp
    origin_state: float
    origin_status: str
    target_state: float
    target_status: str
    features: np.ndarray | None


@dataclass(frozen=True)
class _RidgeModel:
    intercept: float
    coefficients: np.ndarray


@dataclass(frozen=True)
class _FinalForecast:
    channel_id: str
    horizon: int
    status: str
    reason: str | None
    selected_model: str | None
    conditional_means: np.ndarray
    selected_alpha: float
    training_count: int
    training_end: pd.Timestamp | pd.NaT
    calibration_status: str
    evaluation_status: str
    evaluation_count: int
    champion_oos_loss: float
    historical_mean_oos_loss: float
    persistence_oos_loss: float
    origin_state: float
    origin_innovation: float
    origin_uncertainty: float
    data_vintage: pd.Timestamp
    active_cycle_ids: tuple[str, ...]
    missing_cycle_ids: tuple[str, ...]
    feature_labels: tuple[str, ...]
    support_uncertainty_multiplier: float


def _config_hash(config: ChannelForecastConfig) -> str:
    return _stable_hash(asdict(config))


def _channel_registry_hash(forecast_input: ChannelForecastInput) -> str:
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    return _stable_hash(
        [
            channel.model_dump(mode="json")
            for channel in sorted(channel_specs, key=lambda item: item.channel_id)
        ]
    )


def _cycle_provenance(
    forecast_input: ChannelForecastInput,
) -> tuple[str, str, str]:
    cycle_forecast = object.__getattribute__(forecast_input, "cycle_forecast")
    summary = cycle_forecast.summary
    config_hashes = set(summary["forecast_config_hash"])
    registry_hashes = set(summary["registry_hash"])
    if len(config_hashes) != 1 or len(registry_hashes) != 1:
        raise ValueError("cycle forecast provenance is inconsistent")
    return (
        cycle_forecast.config.model_version,
        str(next(iter(config_hashes))),
        str(next(iter(registry_hashes))),
    )


def _cycle_support(
    forecast_input: ChannelForecastInput,
    horizon: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    cycle_forecast = object.__getattribute__(forecast_input, "cycle_forecast")
    paths = cycle_forecast.monthly_paths
    available = set(paths.loc[paths["month_number"].eq(horizon), "cycle_id"].tolist())
    cycle_ids = tuple(cycle.cycle_id for cycle in _cycle_specs(cycle_forecast))
    active = tuple(cycle_id for cycle_id in cycle_ids if cycle_id in available)
    missing = tuple(cycle_id for cycle_id in cycle_ids if cycle_id not in available)
    return active, missing


def _feature_labels(
    active_cycle_ids: tuple[str, ...],
    exogenous_feature_ids: tuple[str, ...],
) -> tuple[str, ...]:
    labels = ["origin_state"]
    for cycle_id in active_cycle_ids:
        labels.extend((f"cycle:{cycle_id}:level", f"cycle:{cycle_id}:slope"))
    labels.extend(f"exog:{feature_id}" for feature_id in exogenous_feature_ids)
    return tuple(labels)


def _historical_lookups(
    forecast_input: ChannelForecastInput,
) -> tuple[
    dict[tuple[pd.Timestamp, int, str], tuple[float, float]],
    dict[tuple[pd.Timestamp, int, str], float],
]:
    cycle_archive = object.__getattribute__(
        forecast_input,
        "cycle_predictor_archive",
    )
    cycle_lookup = {
        (origin, int(horizon), str(cycle_id)): (
            float(group["level"].mean()),
            float(group["slope"].mean()),
        )
        for (origin, horizon, cycle_id), group in cycle_archive.groupby(
            ["forecast_origin", "horizon_months", "cycle_id"],
            sort=False,
        )
    }
    exogenous_archive = object.__getattribute__(
        forecast_input,
        "exogenous_forecast_archive",
    )
    exogenous_lookup = {
        (origin, int(horizon), str(feature_id)): float(group["value"].mean())
        for (origin, horizon, feature_id), group in exogenous_archive.groupby(
            ["forecast_origin", "horizon_months", "feature_id"],
            sort=False,
        )
    }
    return cycle_lookup, exogenous_lookup


def _history_features(
    row: object,
    *,
    active_cycle_ids: tuple[str, ...],
    exogenous_feature_ids: tuple[str, ...],
    cycle_lookup: dict[tuple[pd.Timestamp, int, str], tuple[float, float]],
    exogenous_lookup: dict[tuple[pd.Timestamp, int, str], float],
) -> np.ndarray | None:
    values = [float(row.origin_state)]
    for cycle_id in active_cycle_ids:
        key = (row.forecast_origin, int(row.horizon_months), cycle_id)
        if key not in cycle_lookup:
            return None
        values.extend(cycle_lookup[key])
    for feature_id in exogenous_feature_ids:
        key = (row.forecast_origin, int(row.horizon_months), feature_id)
        if key not in exogenous_lookup:
            return None
        values.append(exogenous_lookup[key])
    features = np.asarray(values, dtype="float64")
    if not np.isfinite(features).all():
        return None
    return features


def _training_samples(
    forecast_input: ChannelForecastInput,
    *,
    channel_id: str,
    horizon: int,
    active_cycle_ids: tuple[str, ...],
    cycle_lookup: dict[tuple[pd.Timestamp, int, str], tuple[float, float]],
    exogenous_lookup: dict[tuple[pd.Timestamp, int, str], float],
) -> list[_TrainingSample]:
    history = object.__getattribute__(forecast_input, "channel_history")
    feature_ids = object.__getattribute__(forecast_input, "exogenous_feature_ids")
    rows = history.loc[
        history["channel_id"].eq(channel_id) & history["horizon_months"].eq(horizon)
    ]
    samples = []
    for row in rows.itertuples(index=False):
        features = None
        if row.origin_status == "available":
            features = _history_features(
                row,
                active_cycle_ids=active_cycle_ids,
                exogenous_feature_ids=feature_ids,
                cycle_lookup=cycle_lookup,
                exogenous_lookup=exogenous_lookup,
            )
        samples.append(
            _TrainingSample(
                forecast_origin=row.forecast_origin,
                target_date=row.target_date,
                target_visible_date=row.target_visible_date,
                target_revision_window_end=row.target_revision_window_end,
                origin_state=float(row.origin_state)
                if row.origin_status == "available"
                else float("nan"),
                origin_status=str(row.origin_status),
                target_state=float(row.target_state)
                if row.target_status == "available"
                else float("nan"),
                target_status=str(row.target_status),
                features=features,
            )
        )
    return samples


def _sample_is_usable(sample: _TrainingSample) -> bool:
    return (
        sample.origin_status == "available"
        and sample.target_status == "available"
        and sample.features is not None
        and np.isfinite(sample.target_state)
    )


def _mature_before(sample: _TrainingSample, cutoff: pd.Timestamp) -> bool:
    return (
        sample.target_visible_date < cutoff
        and sample.target_revision_window_end < cutoff
    )


def _eligible_samples(
    samples: list[_TrainingSample],
    *,
    origin_limit: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> list[_TrainingSample]:
    return [
        sample
        for sample in samples
        if sample.forecast_origin < origin_limit
        and _sample_is_usable(sample)
        and _mature_before(sample, cutoff)
    ]


def _fit_ridge(
    features: np.ndarray,
    target: np.ndarray,
    *,
    alpha: float,
) -> _RidgeModel:
    if features.ndim != 2 or target.ndim != 1 or len(features) != len(target):
        raise ValueError("ridge training arrays have invalid dimensions")
    if (
        len(target) == 0
        or not np.isfinite(features).all()
        or not np.isfinite(target).all()
    ):
        raise ValueError("ridge training arrays must be finite and non-empty")
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0, ddof=0)
    tolerance = np.finfo("float64").eps * max(len(features), 1)
    feature_scale = np.where(feature_scale <= tolerance, 1.0, feature_scale)
    standardized = (features - feature_mean) / feature_scale
    target_mean = float(target.mean())
    centered_target = target - target_mean
    penalized = standardized.T @ standardized + alpha * np.eye(standardized.shape[1])
    standardized_coefficients = (
        np.linalg.pinv(penalized, hermitian=True) @ standardized.T @ centered_target
    )
    coefficients = standardized_coefficients / feature_scale
    intercept = target_mean - float(feature_mean @ coefficients)
    return _RidgeModel(
        intercept=float(intercept),
        coefficients=np.asarray(coefficients, dtype="float64"),
    )


def _predict(model: _RidgeModel, features: np.ndarray) -> float:
    return float(model.intercept + features @ model.coefficients)


def _training_arrays(
    samples: list[_TrainingSample],
) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.vstack([sample.features for sample in samples]),
        np.asarray([sample.target_state for sample in samples], dtype="float64"),
    )


def _select_alpha(
    samples: list[_TrainingSample],
    *,
    config: ChannelForecastConfig,
) -> tuple[float, int, str]:
    scores = {alpha: [] for alpha in config.alpha_grid}
    validation_samples = samples[-config.alpha_validation_window :]
    for validation in validation_samples:
        cutoff = validation.forecast_origin - pd.Timedelta(days=config.embargo_days)
        inner = _eligible_samples(
            samples,
            origin_limit=validation.forecast_origin,
            cutoff=cutoff,
        )
        if len(inner) < config.min_training_count:
            continue
        inner_features, inner_target = _training_arrays(inner)
        for alpha in config.alpha_grid:
            try:
                model = _fit_ridge(inner_features, inner_target, alpha=alpha)
            except (ValueError, np.linalg.LinAlgError):
                continue
            prediction = _predict(model, validation.features)
            scores[alpha].append((validation.target_state - prediction) ** 2)
    eligible = [
        (float(np.mean(losses)), alpha, len(losses))
        for alpha, losses in scores.items()
        if losses
    ]
    if not eligible:
        return (
            float(config.alpha_grid[0]),
            0,
            "default_alpha_insufficient_nested_history",
        )
    _, alpha, count = min(eligible, key=lambda item: (item[0], item[1]))
    return float(alpha), int(count), "walk_forward_selected"


def _winning_model(
    champion_loss: float,
    historical_mean_loss: float,
    persistence_loss: float,
) -> str:
    baseline = min(
        (persistence_loss, "persistence"),
        (historical_mean_loss, "historical_mean"),
        key=lambda item: (item[0], item[1]),
    )
    tolerance = 1e-12 * max(
        1.0,
        abs(champion_loss),
        abs(baseline[0]),
    )
    if champion_loss < baseline[0] - tolerance:
        return "champion"
    return baseline[1]


def _evaluation_rows(
    forecast_input: ChannelForecastInput,
    *,
    config: ChannelForecastConfig,
    samples_by_key: dict[tuple[str, int], list[_TrainingSample]],
    support_by_horizon: dict[
        int,
        tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    ],
) -> pd.DataFrame:
    as_of = pd.Timestamp(forecast_input.as_of)
    current_cutoff = as_of - pd.Timedelta(days=config.embargo_days)
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    config_hash = _config_hash(config)
    registry_hash = _channel_registry_hash(forecast_input)
    records = []
    for channel in channel_specs:
        for horizon in config.horizons:
            active, missing, labels = support_by_horizon[horizon]
            samples = samples_by_key[(channel.channel_id, horizon)]
            for validation in samples:
                embargo_cutoff = validation.forecast_origin - pd.Timedelta(
                    days=config.embargo_days
                )
                training = _eligible_samples(
                    samples,
                    origin_limit=validation.forecast_origin,
                    cutoff=embargo_cutoff,
                )
                training_end = (
                    max(sample.forecast_origin for sample in training)
                    if training
                    else pd.NaT
                )
                record = {
                    "fold_id": (
                        f"{validation.forecast_origin.date().isoformat()}|"
                        f"{channel.channel_id}|h{horizon}"
                    ),
                    "validation_origin": validation.forecast_origin,
                    "target_date": validation.target_date,
                    "channel_id": channel.channel_id,
                    "horizon_months": horizon,
                    "status": "unavailable",
                    "reason": None,
                    "realized_state": float("nan"),
                    "champion_prediction": float("nan"),
                    "historical_mean_prediction": float("nan"),
                    "persistence_prediction": float("nan"),
                    "champion_loss": float("nan"),
                    "historical_mean_loss": float("nan"),
                    "persistence_loss": float("nan"),
                    "selected_model": None,
                    "selected_alpha": float("nan"),
                    "alpha_validation_count": 0,
                    "training_count": len(training),
                    "training_end": training_end,
                    "embargo_cutoff": embargo_cutoff,
                    "feature_labels": labels,
                    "active_cycle_ids": active,
                    "missing_cycle_ids": missing,
                    "forecast_model_version": config.model_version,
                    "forecast_config_hash": config_hash,
                    "channel_registry_hash": registry_hash,
                }
                if not _mature_before(validation, current_cutoff):
                    record["reason"] = "target_not_visible_or_revision_embargoed_as_of"
                    records.append(record)
                    continue
                if validation.target_status != "available":
                    record["reason"] = "target_channel_unavailable"
                    records.append(record)
                    continue
                record["realized_state"] = validation.target_state
                if validation.origin_status != "available":
                    record["reason"] = "origin_channel_unavailable"
                    records.append(record)
                    continue
                if validation.features is None:
                    record["reason"] = "historical_predictor_support_incomplete"
                    records.append(record)
                    continue
                if len(training) < config.min_training_count:
                    record["reason"] = "insufficient_training_history"
                    records.append(record)
                    continue
                alpha, alpha_count, _ = _select_alpha(training, config=config)
                training_features, training_target = _training_arrays(training)
                try:
                    model = _fit_ridge(
                        training_features,
                        training_target,
                        alpha=alpha,
                    )
                except (ValueError, np.linalg.LinAlgError):
                    record["reason"] = "champion_fit_failed"
                    records.append(record)
                    continue
                champion_prediction = _predict(model, validation.features)
                historical_mean_prediction = float(training_target.mean())
                persistence_prediction = validation.origin_state
                champion_loss = (validation.target_state - champion_prediction) ** 2
                historical_mean_loss = (
                    validation.target_state - historical_mean_prediction
                ) ** 2
                persistence_loss = (
                    validation.target_state - persistence_prediction
                ) ** 2
                record.update(
                    {
                        "status": "available",
                        "reason": None,
                        "champion_prediction": champion_prediction,
                        "historical_mean_prediction": historical_mean_prediction,
                        "persistence_prediction": persistence_prediction,
                        "champion_loss": champion_loss,
                        "historical_mean_loss": historical_mean_loss,
                        "persistence_loss": persistence_loss,
                        "selected_model": _winning_model(
                            champion_loss,
                            historical_mean_loss,
                            persistence_loss,
                        ),
                        "selected_alpha": alpha,
                        "alpha_validation_count": alpha_count,
                    }
                )
                records.append(record)
    return (
        pd.DataFrame(records, columns=CHANNEL_FORECAST_EVALUATION_COLUMNS)
        .sort_values(
            ["channel_id", "horizon_months", "validation_origin"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _current_feature_matrix(
    forecast_input: ChannelForecastInput,
    *,
    horizon: int,
    origin_state: float,
    active_cycle_ids: tuple[str, ...],
) -> np.ndarray:
    cycle_forecast = object.__getattribute__(forecast_input, "cycle_forecast")
    paths = cycle_forecast.monthly_paths
    exogenous_paths = object.__getattribute__(
        forecast_input,
        "current_exogenous_paths",
    )
    feature_ids = object.__getattribute__(forecast_input, "exogenous_feature_ids")
    draw_count = cycle_forecast.config.draw_count
    features = []
    for draw_id in range(draw_count):
        row_values = [origin_state]
        for cycle_id in active_cycle_ids:
            matching = paths.loc[
                paths["cycle_id"].eq(cycle_id)
                & paths["month_number"].eq(horizon)
                & paths["draw_id"].eq(draw_id)
            ]
            if len(matching) != 1:
                raise ValueError("current cycle draw coverage is incomplete")
            row_values.extend(
                (
                    float(matching.iloc[0]["level"]),
                    float(matching.iloc[0]["slope"]),
                )
            )
        for feature_id in feature_ids:
            matching = exogenous_paths.loc[
                exogenous_paths["feature_id"].eq(feature_id)
                & exogenous_paths["horizon_months"].eq(horizon)
            ]
            if matching.empty:
                raise ValueError("current exogenous horizon coverage is incomplete")
            if bool(matching.iloc[0]["is_deterministic"]):
                value = float(matching.iloc[0]["value"])
            else:
                draw = matching.loc[matching["draw_id"].eq(draw_id)]
                if len(draw) != 1:
                    raise ValueError("current exogenous draw_id coverage is incomplete")
                value = float(draw.iloc[0]["value"])
            row_values.append(value)
        features.append(row_values)
    matrix = np.asarray(features, dtype="float64")
    if not np.isfinite(matrix).all():
        raise ValueError("current channel forecast features must be finite")
    return matrix


def _mean_losses(
    evaluation: pd.DataFrame,
    *,
    channel_id: str,
    horizon: int,
) -> tuple[int, float, float, float]:
    available = evaluation.loc[
        evaluation["channel_id"].eq(channel_id)
        & evaluation["horizon_months"].eq(horizon)
        & evaluation["status"].eq("available")
    ]
    if available.empty:
        return 0, float("nan"), float("nan"), float("nan")
    return (
        len(available),
        float(available["champion_loss"].mean()),
        float(available["historical_mean_loss"].mean()),
        float(available["persistence_loss"].mean()),
    )


def _final_forecasts(
    forecast_input: ChannelForecastInput,
    *,
    config: ChannelForecastConfig,
    evaluation: pd.DataFrame,
    samples_by_key: dict[tuple[str, int], list[_TrainingSample]],
    support_by_horizon: dict[
        int,
        tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    ],
) -> dict[tuple[str, int], _FinalForecast]:
    as_of = pd.Timestamp(forecast_input.as_of)
    cutoff = as_of - pd.Timedelta(days=config.embargo_days)
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    current_states = object.__getattribute__(
        forecast_input,
        "current_channel_states",
    ).set_index("channel_id")
    draw_count = forecast_input.cycle_forecast.config.draw_count
    cycle_count = len(_cycle_specs(forecast_input.cycle_forecast))
    forecasts = {}
    for channel in channel_specs:
        state = current_states.loc[channel.channel_id]
        for horizon in config.horizons:
            active, missing, labels = support_by_horizon[horizon]
            support_multiplier = 1.0 + len(missing) / max(cycle_count, 1)
            samples = samples_by_key[(channel.channel_id, horizon)]
            training = _eligible_samples(
                samples,
                origin_limit=as_of,
                cutoff=cutoff,
            )
            training_end = (
                max(sample.forecast_origin for sample in training)
                if training
                else pd.NaT
            )
            evaluation_count, champion_loss, mean_loss, persistence_loss = _mean_losses(
                evaluation,
                channel_id=channel.channel_id,
                horizon=horizon,
            )
            if state["status"] != "available":
                forecasts[(channel.channel_id, horizon)] = _FinalForecast(
                    channel_id=channel.channel_id,
                    horizon=horizon,
                    status="unavailable",
                    reason=str(state["status_reason"]),
                    selected_model=None,
                    conditional_means=np.full(draw_count, np.nan),
                    selected_alpha=float("nan"),
                    training_count=len(training),
                    training_end=training_end,
                    calibration_status="unavailable",
                    evaluation_status=(
                        "available" if evaluation_count else "insufficient_oos_history"
                    ),
                    evaluation_count=evaluation_count,
                    champion_oos_loss=champion_loss,
                    historical_mean_oos_loss=mean_loss,
                    persistence_oos_loss=persistence_loss,
                    origin_state=float("nan"),
                    origin_innovation=float("nan"),
                    origin_uncertainty=float("nan"),
                    data_vintage=state["data_vintage"],
                    active_cycle_ids=active,
                    missing_cycle_ids=missing,
                    feature_labels=labels,
                    support_uncertainty_multiplier=support_multiplier,
                )
                continue
            origin_state = float(state["state"])
            selected_alpha = float(config.alpha_grid[0])
            calibration_status = "default_alpha_insufficient_nested_history"
            champion_model = None
            training_target = np.asarray(
                [sample.target_state for sample in training],
                dtype="float64",
            )
            if len(training) >= config.min_training_count:
                selected_alpha, _, calibration_status = _select_alpha(
                    training,
                    config=config,
                )
                training_features, training_target = _training_arrays(training)
                try:
                    champion_model = _fit_ridge(
                        training_features,
                        training_target,
                        alpha=selected_alpha,
                    )
                except (ValueError, np.linalg.LinAlgError):
                    champion_model = None
                    calibration_status = "champion_fit_failed"
            selected_model = "persistence"
            if evaluation_count:
                selected_model = _winning_model(
                    champion_loss,
                    mean_loss,
                    persistence_loss,
                )
            if selected_model == "champion" and champion_model is None:
                selected_model = "persistence"
            if selected_model == "historical_mean" and training_target.size == 0:
                selected_model = "persistence"
            if selected_model == "champion":
                current_features = _current_feature_matrix(
                    forecast_input,
                    horizon=horizon,
                    origin_state=origin_state,
                    active_cycle_ids=active,
                )
                conditional_means = (
                    champion_model.intercept
                    + current_features @ champion_model.coefficients
                )
            elif selected_model == "historical_mean":
                conditional_means = np.full(
                    draw_count,
                    float(training_target.mean()),
                    dtype="float64",
                )
            else:
                conditional_means = np.full(
                    draw_count,
                    origin_state,
                    dtype="float64",
                )
            forecasts[(channel.channel_id, horizon)] = _FinalForecast(
                channel_id=channel.channel_id,
                horizon=horizon,
                status="available",
                reason=None,
                selected_model=selected_model,
                conditional_means=np.asarray(conditional_means, dtype="float64"),
                selected_alpha=selected_alpha,
                training_count=len(training),
                training_end=training_end,
                calibration_status=calibration_status,
                evaluation_status=(
                    "available" if evaluation_count else "insufficient_oos_history"
                ),
                evaluation_count=evaluation_count,
                champion_oos_loss=champion_loss,
                historical_mean_oos_loss=mean_loss,
                persistence_oos_loss=persistence_loss,
                origin_state=origin_state,
                origin_innovation=float(state["innovation"]),
                origin_uncertainty=float(state["uncertainty"]),
                data_vintage=state["data_vintage"],
                active_cycle_ids=active,
                missing_cycle_ids=missing,
                feature_labels=labels,
                support_uncertainty_multiplier=support_multiplier,
            )
    return forecasts


def _repair_psd(values: np.ndarray) -> np.ndarray:
    symmetric = (values + values.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    repaired = eigenvectors @ np.diag(np.clip(eigenvalues, 0.0, None)) @ eigenvectors.T
    return (repaired + repaired.T) / 2.0


def _residual_covariance(
    evaluation: pd.DataFrame,
    *,
    horizon: int,
    channel_ids: tuple[str, ...],
    selected_models: dict[str, str],
    current_states: pd.DataFrame,
    support_multiplier: float,
    config: ChannelForecastConfig,
) -> tuple[np.ndarray, int, str, str, str | None]:
    available = evaluation.loc[
        evaluation["horizon_months"].eq(horizon)
        & evaluation["status"].eq("available")
        & evaluation["channel_id"].isin(channel_ids)
    ].copy()
    prediction_columns = {
        "champion": "champion_prediction",
        "historical_mean": "historical_mean_prediction",
        "persistence": "persistence_prediction",
    }
    selected_residuals = []
    for row in available.itertuples(index=False):
        selected_model = selected_models.get(row.channel_id)
        if selected_model not in prediction_columns:
            raise ValueError("available channels require a selected residual model")
        prediction = getattr(row, prediction_columns[selected_model])
        selected_residuals.append(float(row.realized_state - prediction))
    available["selected_model_residual"] = selected_residuals
    pivot = available.pivot(
        index="validation_origin",
        columns="channel_id",
        values="selected_model_residual",
    )
    pivot = pivot.reindex(columns=channel_ids).dropna(how="any")
    sample_count = len(pivot)
    if sample_count >= config.covariance_min_samples and sample_count >= 2:
        raw = np.atleast_2d(
            np.cov(pivot.to_numpy(dtype="float64"), rowvar=False, ddof=1)
        )
        diagonal = np.diag(np.diag(raw))
        covariance = (
            1.0 - config.covariance_shrinkage
        ) * raw + config.covariance_shrinkage * diagonal
        return (
            _repair_psd(covariance * support_multiplier),
            sample_count,
            "shrunk_oos_selected_model_residual",
            "estimated",
            None,
        )
    variances = []
    indexed_states = current_states.set_index("channel_id")
    for channel_id in channel_ids:
        residuals = available.loc[
            available["channel_id"].eq(channel_id),
            "selected_model_residual",
        ].dropna()
        if len(residuals) >= 2:
            variance = float(residuals.var(ddof=1))
        else:
            uncertainty = indexed_states.loc[channel_id, "uncertainty"]
            variance = (
                float(uncertainty) ** 2
                if np.isfinite(float(uncertainty))
                else config.fallback_variance_floor
            )
        variances.append(max(variance, config.fallback_variance_floor))
    return (
        np.diag(np.asarray(variances, dtype="float64")) * support_multiplier,
        sample_count,
        "diagonal_fallback",
        "fallback",
        "insufficient_aligned_oos_selected_model_residual_samples",
    )


def _joint_residual_draws(
    covariance: np.ndarray,
    *,
    draw_count: int,
    seed: int,
    horizon: int,
) -> np.ndarray:
    channel_count = covariance.shape[0]
    if draw_count <= 1:
        return np.zeros((draw_count, channel_count), dtype="float64")
    random = np.random.default_rng(np.random.SeedSequence([seed, horizon]))
    standard = random.standard_normal((draw_count, channel_count))
    standard -= standard.mean(axis=0, keepdims=True)
    sample_covariance = np.atleast_2d(np.cov(standard, rowvar=False, ddof=1))
    eigenvalues, eigenvectors = np.linalg.eigh(sample_covariance)
    tolerance = np.finfo("float64").eps * max(channel_count, draw_count)
    inverse_sqrt = np.zeros_like(eigenvalues)
    supported = eigenvalues > tolerance
    inverse_sqrt[supported] = 1.0 / np.sqrt(eigenvalues[supported])
    inverse_root = (
        eigenvectors
        @ np.diag(inverse_sqrt)
        @ eigenvectors.T
    )
    whitened = standard @ inverse_root
    target_values, target_vectors = np.linalg.eigh(_repair_psd(covariance))
    target_root = (
        target_vectors
        @ np.diag(np.sqrt(np.clip(target_values, 0.0, None)))
        @ target_vectors.T
    )
    residuals = whitened @ target_root
    residuals -= residuals.mean(axis=0, keepdims=True)
    return np.asarray(residuals, dtype="float64")


def _correlation(covariance: float, variance_i: float, variance_j: float) -> float:
    if not np.isfinite(covariance) or not np.isfinite(variance_i + variance_j):
        return float("nan")
    denominator = np.sqrt(max(variance_i, 0.0) * max(variance_j, 0.0))
    if denominator <= 0.0:
        return 0.0
    return float(np.clip(covariance / denominator, -1.0, 1.0))


def _draws_and_covariance(
    forecast_input: ChannelForecastInput,
    *,
    config: ChannelForecastConfig,
    evaluation: pd.DataFrame,
    forecasts: dict[tuple[str, int], _FinalForecast],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[tuple[str, int], tuple[str, str, int]],
]:
    as_of = pd.Timestamp(forecast_input.as_of)
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    channel_ids = tuple(channel.channel_id for channel in channel_specs)
    channel_positions = {
        channel_id: position for position, channel_id in enumerate(channel_ids)
    }
    current_states = object.__getattribute__(
        forecast_input,
        "current_channel_states",
    )
    draw_count = forecast_input.cycle_forecast.config.draw_count
    config_hash = _config_hash(config)
    registry_hash = _channel_registry_hash(forecast_input)
    cycle_model, cycle_config_hash, cycle_registry_hash = _cycle_provenance(
        forecast_input
    )
    draw_records = []
    covariance_records = []
    covariance_metadata = {}
    for horizon in config.horizons:
        support_multiplier = forecasts[
            (channel_ids[0], horizon)
        ].support_uncertainty_multiplier
        available_channel_ids = tuple(
            channel_id
            for channel_id in channel_ids
            if forecasts[(channel_id, horizon)].status == "available"
        )
        available_positions = {
            channel_id: position
            for position, channel_id in enumerate(available_channel_ids)
        }
        if available_channel_ids:
            selected_models = {}
            for channel_id in available_channel_ids:
                selected_model = forecasts[(channel_id, horizon)].selected_model
                if selected_model is None:
                    raise ValueError(
                        "available channels require a selected residual model"
                    )
                selected_models[channel_id] = selected_model
            residual_covariance, sample_count, method, status, fallback_reason = (
                _residual_covariance(
                    evaluation,
                    horizon=horizon,
                    channel_ids=available_channel_ids,
                    selected_models=selected_models,
                    current_states=current_states,
                    support_multiplier=support_multiplier,
                    config=config,
                )
            )
            residual_draws = _joint_residual_draws(
                residual_covariance,
                draw_count=draw_count,
                seed=config.seed,
                horizon=horizon,
            )
        else:
            sample_count = 0
            method = "not_estimated"
            status = "unavailable"
            fallback_reason = "current_channel_unavailable"
            residual_draws = np.empty((draw_count, 0), dtype="float64")
        for channel_id in channel_ids:
            forecast = forecasts[(channel_id, horizon)]
            for draw_id in range(draw_count):
                residual = (
                    float(residual_draws[draw_id, available_positions[channel_id]])
                    if forecast.status == "available"
                    else float("nan")
                )
                conditional_mean = (
                    float(forecast.conditional_means[draw_id])
                    if forecast.status == "available"
                    else float("nan")
                )
                forecast_state = (
                    conditional_mean + residual
                    if forecast.status == "available"
                    else float("nan")
                )
                draw_records.append(
                    {
                        "as_of": as_of,
                        "forecast_date": _forecast_date(as_of, horizon),
                        "channel_id": channel_id,
                        "draw_id": draw_id,
                        "cycle_draw_id": draw_id,
                        "horizon_months": horizon,
                        "status": forecast.status,
                        "unavailable_reason": forecast.reason,
                        "selected_model": forecast.selected_model,
                        "forecast_state": forecast_state,
                        "forecast_innovation": (
                            forecast_state - forecast.origin_state
                            if forecast.status == "available"
                            else float("nan")
                        ),
                        "forecast_mean": conditional_mean,
                        "residual": residual,
                        "origin_state": forecast.origin_state,
                        "active_cycle_ids": forecast.active_cycle_ids,
                        "missing_cycle_ids": forecast.missing_cycle_ids,
                        "feature_labels": forecast.feature_labels,
                        "model_role": (
                            "champion"
                            if forecast.selected_model == "champion"
                            else "baseline"
                        ),
                        "forecast_model_version": config.model_version,
                        "forecast_config_hash": config_hash,
                        "channel_registry_hash": registry_hash,
                        "cycle_forecast_model_version": cycle_model,
                        "cycle_forecast_config_hash": cycle_config_hash,
                        "cycle_registry_hash": cycle_registry_hash,
                        "data_vintage": forecast.data_vintage,
                    }
                )
        published_residual_covariance = np.full(
            (len(channel_ids), len(channel_ids)),
            np.nan,
            dtype="float64",
        )
        if available_channel_ids:
            available_covariance = np.atleast_2d(
                np.cov(residual_draws, rowvar=False, ddof=1)
            )
            available_covariance = (available_covariance + available_covariance.T) / 2.0
            full_positions = [
                channel_positions[channel_id] for channel_id in available_channel_ids
            ]
            published_residual_covariance[np.ix_(full_positions, full_positions)] = (
                available_covariance
            )
        variances = np.diag(published_residual_covariance)
        data_vintage = current_states["data_vintage"].max()
        for row_position, channel_i in enumerate(channel_ids):
            for column_position, channel_j in enumerate(channel_ids):
                pair_available = (
                    channel_i in available_positions
                    and channel_j in available_positions
                )
                covariance_value = (
                    float(
                        published_residual_covariance[
                            row_position,
                            column_position,
                        ]
                    )
                    if pair_available
                    else float("nan")
                )
                covariance_records.append(
                    {
                        "as_of": as_of,
                        "forecast_date": _forecast_date(as_of, horizon),
                        "horizon_months": horizon,
                        "channel_i": channel_i,
                        "channel_j": channel_j,
                        "covariance": covariance_value,
                        "correlation": _correlation(
                            covariance_value,
                            float(variances[row_position]),
                            float(variances[column_position]),
                        ),
                        "sample_count": sample_count if pair_available else 0,
                        "method": method if pair_available else "not_estimated",
                        "status": status if pair_available else "unavailable",
                        "fallback_reason": (
                            fallback_reason
                            if pair_available
                            else "current_channel_unavailable"
                        ),
                        "support_uncertainty_multiplier": support_multiplier,
                        "forecast_model_version": config.model_version,
                        "forecast_config_hash": config_hash,
                        "channel_registry_hash": registry_hash,
                        "data_vintage": data_vintage,
                    }
                )
        for channel_id in channel_ids:
            covariance_metadata[(channel_id, horizon)] = (
                (status, method, sample_count)
                if channel_id in available_positions
                else ("unavailable", "not_estimated", 0)
            )
    draws = (
        pd.DataFrame(draw_records, columns=CHANNEL_FORECAST_DRAW_COLUMNS)
        .sort_values(
            ["channel_id", "horizon_months", "draw_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    covariance = (
        pd.DataFrame(
            covariance_records,
            columns=CHANNEL_FORECAST_COVARIANCE_COLUMNS,
        )
        .sort_values(
            ["horizon_months", "channel_i", "channel_j"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return draws, covariance, covariance_metadata


def _summary_rows(
    forecast_input: ChannelForecastInput,
    *,
    config: ChannelForecastConfig,
    forecasts: dict[tuple[str, int], _FinalForecast],
    draws: pd.DataFrame,
    covariance_metadata: dict[tuple[str, int], tuple[str, str, int]],
) -> pd.DataFrame:
    as_of = pd.Timestamp(forecast_input.as_of)
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    config_hash = _config_hash(config)
    registry_hash = _channel_registry_hash(forecast_input)
    cycle_model, cycle_config_hash, cycle_registry_hash = _cycle_provenance(
        forecast_input
    )
    records = []
    for channel in channel_specs:
        for horizon in config.horizons:
            forecast = forecasts[(channel.channel_id, horizon)]
            retained = draws.loc[
                draws["channel_id"].eq(channel.channel_id)
                & draws["horizon_months"].eq(horizon)
            ]
            if forecast.status == "available":
                states = retained["forecast_state"].to_numpy(dtype="float64")
                innovations = retained["forecast_innovation"].to_numpy(dtype="float64")
                quantiles = np.quantile(states, [0.10, 0.25, 0.50, 0.75, 0.90])
                forecast_mean = float(states.mean())
                forecast_std = float(states.std(ddof=1)) if len(states) >= 2 else 0.0
                innovation_mean = float(innovations.mean())
                probability_positive = float(np.mean(states >= 0.0))
                probability_negative = 1.0 - probability_positive
            else:
                quantiles = np.full(5, np.nan)
                forecast_mean = float("nan")
                forecast_std = float("nan")
                innovation_mean = float("nan")
                probability_positive = float("nan")
                probability_negative = float("nan")
            covariance_status, covariance_method, covariance_count = (
                covariance_metadata[(channel.channel_id, horizon)]
            )
            records.append(
                {
                    "as_of": as_of,
                    "forecast_date": _forecast_date(as_of, horizon),
                    "channel_id": channel.channel_id,
                    "horizon_months": horizon,
                    "status": forecast.status,
                    "unavailable_reason": forecast.reason,
                    "selected_model": forecast.selected_model,
                    "forecast_mean": forecast_mean,
                    "forecast_std": forecast_std,
                    "innovation_mean": innovation_mean,
                    "q10": float(quantiles[0]),
                    "q25": float(quantiles[1]),
                    "q50": float(quantiles[2]),
                    "q75": float(quantiles[3]),
                    "q90": float(quantiles[4]),
                    "probability_positive": probability_positive,
                    "probability_negative": probability_negative,
                    "origin_state": forecast.origin_state,
                    "origin_innovation": forecast.origin_innovation,
                    "origin_uncertainty": forecast.origin_uncertainty,
                    "active_cycle_count": len(forecast.active_cycle_ids),
                    "active_cycle_ids": forecast.active_cycle_ids,
                    "missing_cycle_ids": forecast.missing_cycle_ids,
                    "support_uncertainty_multiplier": (
                        forecast.support_uncertainty_multiplier
                    ),
                    "feature_labels": forecast.feature_labels,
                    "selected_alpha": forecast.selected_alpha,
                    "training_count": forecast.training_count,
                    "training_end": forecast.training_end,
                    "embargo_cutoff": as_of - pd.Timedelta(days=config.embargo_days),
                    "calibration_status": forecast.calibration_status,
                    "evaluation_status": forecast.evaluation_status,
                    "evaluation_fold_count": forecast.evaluation_count,
                    "champion_oos_loss": forecast.champion_oos_loss,
                    "historical_mean_oos_loss": (forecast.historical_mean_oos_loss),
                    "persistence_oos_loss": forecast.persistence_oos_loss,
                    "covariance_status": covariance_status,
                    "covariance_method": covariance_method,
                    "covariance_sample_count": covariance_count,
                    "model_role": (
                        "champion"
                        if forecast.selected_model == "champion"
                        else "baseline"
                    ),
                    "forecast_model_version": config.model_version,
                    "forecast_config_hash": config_hash,
                    "channel_registry_hash": registry_hash,
                    "cycle_forecast_model_version": cycle_model,
                    "cycle_forecast_config_hash": cycle_config_hash,
                    "cycle_registry_hash": cycle_registry_hash,
                    "data_vintage": forecast.data_vintage,
                }
            )
    return (
        pd.DataFrame(records, columns=CHANNEL_FORECAST_SUMMARY_COLUMNS)
        .sort_values(
            ["channel_id", "horizon_months"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _validate_config_coverage(
    forecast_input: ChannelForecastInput,
    config: ChannelForecastConfig,
) -> None:
    feature_ids = object.__getattribute__(forecast_input, "exogenous_feature_ids")
    if not feature_ids:
        return
    current_paths = object.__getattribute__(
        forecast_input,
        "current_exogenous_paths",
    )
    if set(current_paths["horizon_months"]) != set(config.horizons):
        raise ValueError(
            "current exogenous horizon coverage must exactly match config horizons"
        )


def _generate_outputs(
    forecast_input: ChannelForecastInput,
    config: ChannelForecastConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _validate_config_coverage(forecast_input, config)
    cycle_lookup, exogenous_lookup = _historical_lookups(forecast_input)
    feature_ids = object.__getattribute__(forecast_input, "exogenous_feature_ids")
    channel_specs = object.__getattribute__(forecast_input, "channel_specs")
    support_by_horizon = {}
    samples_by_key = {}
    for horizon in config.horizons:
        active, missing = _cycle_support(forecast_input, horizon)
        labels = _feature_labels(active, feature_ids)
        support_by_horizon[horizon] = (active, missing, labels)
        for channel in channel_specs:
            samples_by_key[(channel.channel_id, horizon)] = _training_samples(
                forecast_input,
                channel_id=channel.channel_id,
                horizon=horizon,
                active_cycle_ids=active,
                cycle_lookup=cycle_lookup,
                exogenous_lookup=exogenous_lookup,
            )
    evaluation = _evaluation_rows(
        forecast_input,
        config=config,
        samples_by_key=samples_by_key,
        support_by_horizon=support_by_horizon,
    )
    forecasts = _final_forecasts(
        forecast_input,
        config=config,
        evaluation=evaluation,
        samples_by_key=samples_by_key,
        support_by_horizon=support_by_horizon,
    )
    draws, covariance, covariance_metadata = _draws_and_covariance(
        forecast_input,
        config=config,
        evaluation=evaluation,
        forecasts=forecasts,
    )
    summary = _summary_rows(
        forecast_input,
        config=config,
        forecasts=forecasts,
        draws=draws,
        covariance_metadata=covariance_metadata,
    )
    return summary, draws, covariance, evaluation


def _canonical_result_frame(
    values: object,
    *,
    name: str,
) -> pd.DataFrame:
    columns, sort_keys = _RESULT_SPECS[name]
    frame = _required_frame(values, name=name, columns=columns)
    if frame.duplicated(sort_keys).any():
        raise ValueError(f"{name} contains duplicate result dimensions")
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty and np.isinf(numeric.to_numpy(dtype="float64")).any():
        raise ValueError(f"{name} numeric values cannot be infinite")
    return frame.sort_values(sort_keys, kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class ChannelForecastResult:
    """Detached channel distributions rebuilt from retained inputs and seed."""

    summary: pd.DataFrame
    draws: pd.DataFrame
    covariance: pd.DataFrame
    evaluation: pd.DataFrame
    forecast_input: ChannelForecastInput
    config: ChannelForecastConfig

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_input, ChannelForecastInput):
            raise TypeError("forecast_input must be a ChannelForecastInput")
        if not isinstance(self.config, ChannelForecastConfig):
            raise TypeError("config must be a ChannelForecastConfig")
        supplied = {
            name: _canonical_result_frame(
                object.__getattribute__(self, name),
                name=name,
            )
            for name in _RESULT_SPECS
        }
        generated = dict(
            zip(
                ("summary", "draws", "covariance", "evaluation"),
                _generate_outputs(self.forecast_input, self.config),
                strict=True,
            )
        )
        for name, expected in generated.items():
            expected = _canonical_result_frame(expected, name=name)
            try:
                pd.testing.assert_frame_equal(
                    supplied[name],
                    expected,
                    check_dtype=True,
                    check_exact=True,
                )
            except AssertionError as error:
                raise ValueError(
                    f"{name} is inconsistent with retained channel forecast inputs"
                ) from error
            object.__setattr__(self, name, expected.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.summary

    @property
    def retained_draws(self) -> pd.DataFrame:
        return self.draws

    @property
    def residual_covariance(self) -> pd.DataFrame:
        return self.covariance


def forecast_transmission_channels(
    forecast_input: ChannelForecastInput,
    *,
    config: ChannelForecastConfig | None = None,
) -> ChannelForecastResult:
    """Forecast governed channel states with point-in-time direct-horizon ARX."""

    if not isinstance(forecast_input, ChannelForecastInput):
        raise TypeError("forecast_input must be a ChannelForecastInput")
    normalized_config = config or ChannelForecastConfig()
    if not isinstance(normalized_config, ChannelForecastConfig):
        raise TypeError("config must be a ChannelForecastConfig")
    summary, draws, covariance, evaluation = _generate_outputs(
        forecast_input,
        normalized_config,
    )
    return ChannelForecastResult(
        summary=summary,
        draws=draws,
        covariance=covariance,
        evaluation=evaluation,
        forecast_input=forecast_input,
        config=normalized_config,
    )


__all__ = [
    "CHANNEL_FORECAST_COVARIANCE_COLUMNS",
    "CHANNEL_FORECAST_DRAW_COLUMNS",
    "CHANNEL_FORECAST_EVALUATION_COLUMNS",
    "CHANNEL_FORECAST_SUMMARY_COLUMNS",
    "CHANNEL_HISTORY_COLUMNS",
    "CURRENT_CHANNEL_STATE_COLUMNS",
    "CURRENT_EXOGENOUS_PATH_COLUMNS",
    "CYCLE_PREDICTOR_ARCHIVE_COLUMNS",
    "EXOGENOUS_FORECAST_ARCHIVE_COLUMNS",
    "ChannelForecastConfig",
    "ChannelForecastInput",
    "ChannelForecastResult",
    "forecast_transmission_channels",
]
