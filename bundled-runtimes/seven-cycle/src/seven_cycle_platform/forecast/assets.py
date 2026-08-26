"""Future joint asset distributions driven by governed channel forecasts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import hashlib
import json
from numbers import Integral, Real

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.stage2 import ChannelToAssetResult
from seven_cycle_platform.forecast.channels import (
    ChannelForecastResult,
)
from seven_cycle_platform.forecast.scenarios import (
    ScenarioCatalog,
    resolve_scenario_shocks,
    validate_standard_scenario_catalog,
)
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk


HORIZONS = (3, 6, 12)
RETURN_BASES = ("absolute", "excess")

VALUATION_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "component_id",
    "draw_id",
    "valuation_value",
    "unit",
    "path_kind",
    "model_version",
)
POSITIONING_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "component_id",
    "draw_id",
    "positioning_value",
    "unit",
    "path_kind",
    "model_version",
)
CONTROL_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "component_id",
    "draw_id",
    "control_value",
    "unit",
    "path_kind",
    "model_version",
)
INTERACTION_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "component_id",
    "draw_id",
    "interaction_value",
    "unit",
    "path_kind",
    "model_version",
)
EVENT_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "component_id",
    "draw_id",
    "event_value",
    "unit",
    "path_kind",
    "model_version",
)
BENCHMARK_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "draw_id",
    "benchmark_return",
    "unit",
    "path_kind",
    "model_version",
)
RESIDUAL_FORECAST_INPUT_COLUMNS = (
    "forecast_origin",
    "date",
    "visible_date",
    "generated_date",
    "data_vintage",
    "asset_id",
    "draw_id",
    "residual_return",
    "unit",
    "path_kind",
    "model_version",
)

SCENARIO_CHANNEL_PATH_COLUMNS = (
    "scenario_id",
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "channel_id",
    "draw_id",
    "month_number",
    "date",
    "forecast_origin",
    "status",
    "unavailable_reason",
    "origin_channel_state",
    "baseline_channel_state",
    "baseline_channel_innovation",
    "scenario_shock",
    "adjusted_channel_innovation",
    "adjusted_channel_state",
    "shock_id",
    "shock_version",
    "shock_unit",
    "shock_direction",
    "shock_path",
    "channel_forecast_model_version",
    "channel_forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "data_vintage",
)
ASSET_FORECAST_COMPONENT_COLUMNS = (
    "asset_id",
    "scenario_id",
    "draw_id",
    "month_number",
    "date",
    "forecast_origin",
    "stage2_posterior_date",
    "status",
    "component_type",
    "component_id",
    "source_type",
    "baseline_predictor_value",
    "scenario_predictor_value",
    "adjusted_predictor_value",
    "coefficient_mean",
    "coefficient_draw",
    "baseline_contribution",
    "scenario_contribution",
    "contribution",
    "cycle_contribution",
    "visible_date",
    "generated_date",
    "data_vintage",
    "unit",
    "input_model_version",
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "asset_forecast_model_version",
    "asset_forecast_config_hash",
)
ASSET_FORECAST_MONTHLY_COLUMNS = (
    "asset_id",
    "scenario_id",
    "draw_id",
    "month_number",
    "date",
    "forecast_origin",
    "stage2_posterior_date",
    "baseline_asset_monthly_return",
    "asset_monthly_return",
    "benchmark_monthly_return",
    "relative_monthly_return",
    "intercept_contribution",
    "benchmark_contribution",
    "channel_contribution",
    "valuation_contribution",
    "positioning_contribution",
    "control_contribution",
    "interaction_contribution",
    "event_contribution",
    "scenario_contribution",
    "residual_contribution",
    "cycle_contribution",
    "status",
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "asset_forecast_model_version",
    "asset_forecast_config_hash",
    "channel_forecast_model_version",
    "channel_forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "stage2_estimation_method",
    "data_vintage",
    "feature_visible_date",
    "feature_generated_date",
    "feature_vintage_date",
    "model_provenance",
    "data_provenance",
)
ASSET_FORECAST_DRAW_COLUMNS = (
    "asset_id",
    "scenario_id",
    "draw_id",
    "horizon_months",
    "forecast_origin",
    "stage2_posterior_date",
    "absolute_return",
    "baseline_absolute_return",
    "scenario_return_effect",
    "benchmark_return",
    "excess_return",
    "absolute_max_drawdown",
    "excess_max_drawdown",
    "status",
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "asset_forecast_model_version",
    "asset_forecast_config_hash",
    "channel_forecast_model_version",
    "channel_forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "stage2_estimation_method",
    "data_vintage",
    "feature_visible_date",
    "feature_generated_date",
    "feature_vintage_date",
    "model_provenance",
    "data_provenance",
)
ASSET_FORECAST_SUMMARY_COLUMNS = (
    "asset_id",
    "scenario_id",
    "horizon_months",
    "return_basis",
    "q10",
    "q25",
    "q50",
    "median",
    "q75",
    "q90",
    "interval50_lower",
    "interval50_upper",
    "interval80_lower",
    "interval80_upper",
    "expected_return",
    "volatility",
    "var95",
    "cvar95",
    "drawdown_q50",
    "drawdown_q80",
    "drawdown_q95",
    "effective_samples",
    "stage2_effective_training_count",
    "channel_training_count",
    "status",
    "unavailable_reason",
    "scenario_version",
    "catalog_version",
    "scenario_config_hash",
    "asset_forecast_model_version",
    "asset_forecast_config_hash",
    "channel_forecast_model_version",
    "channel_forecast_config_hash",
    "channel_registry_hash",
    "cycle_forecast_model_version",
    "cycle_forecast_config_hash",
    "cycle_registry_hash",
    "stage2_posterior_date",
    "stage2_estimation_method",
    "forecast_origin",
    "data_vintage",
    "feature_visible_date",
    "feature_generated_date",
    "feature_vintage_date",
    "model_provenance",
    "data_provenance",
)

_INPUT_FRAME_FIELDS = frozenset(
    {
        "valuation_forecasts",
        "positioning_forecasts",
        "control_forecasts",
        "interaction_forecasts",
        "event_forecasts",
        "benchmark_forecasts",
        "residual_forecasts",
    }
)
_RESULT_FRAME_FIELDS = frozenset(
    {"summary", "monthly_draws", "draws", "components", "channel_paths"}
)
_USABLE_STAGE2_STATUSES = frozenset({"estimated", "parent_informed", "parent_only"})
_COMPONENT_ORDER = {
    "intercept": 0,
    "benchmark": 1,
    "channel": 2,
    "interaction": 3,
    "control": 4,
    "event": 5,
}
_SOURCE_ORDER = {
    "intercept": 0,
    "benchmark": 1,
    "channel": 2,
    "valuation": 3,
    "positioning": 4,
    "control": 5,
    "interaction": 6,
    "event": 7,
    "residual": 8,
}
_FRAME_SPECS = {
    "valuation_forecasts": (
        VALUATION_FORECAST_INPUT_COLUMNS,
        "valuation_value",
        True,
    ),
    "positioning_forecasts": (
        POSITIONING_FORECAST_INPUT_COLUMNS,
        "positioning_value",
        True,
    ),
    "control_forecasts": (
        CONTROL_FORECAST_INPUT_COLUMNS,
        "control_value",
        True,
    ),
    "interaction_forecasts": (
        INTERACTION_FORECAST_INPUT_COLUMNS,
        "interaction_value",
        True,
    ),
    "event_forecasts": (EVENT_FORECAST_INPUT_COLUMNS, "event_value", True),
    "benchmark_forecasts": (
        BENCHMARK_FORECAST_INPUT_COLUMNS,
        "benchmark_return",
        False,
    ),
    "residual_forecasts": (
        RESIDUAL_FORECAST_INPUT_COLUMNS,
        "residual_return",
        False,
    ),
}
_RESULT_SPECS = {
    "channel_paths": (
        SCENARIO_CHANNEL_PATH_COLUMNS,
        ["channel_id", "draw_id", "month_number"],
    ),
    "components": (
        ASSET_FORECAST_COMPONENT_COLUMNS,
        [
            "asset_id",
            "draw_id",
            "month_number",
            "component_type",
            "component_id",
        ],
    ),
    "monthly_draws": (
        ASSET_FORECAST_MONTHLY_COLUMNS,
        ["asset_id", "draw_id", "month_number"],
    ),
    "draws": (
        ASSET_FORECAST_DRAW_COLUMNS,
        ["asset_id", "draw_id", "horizon_months"],
    ),
    "summary": (
        ASSET_FORECAST_SUMMARY_COLUMNS,
        ["asset_id", "horizon_months", "return_basis"],
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


def _positive_real(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a positive finite real number")
    numeric = float(value)
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be a positive finite real number")
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


def _nonnegative_floor(value: object, *, name: str) -> int:
    numeric = _finite_real(value, name=name)
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return int(np.floor(numeric))


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value.strip()


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
    if tuple(values.columns) != columns:
        raise ValueError(f"{name} columns do not match the forecast contract")
    return values.copy(deep=True)


def _future_dates(as_of: date, months: int) -> pd.DatetimeIndex:
    first = pd.Timestamp(as_of) + pd.offsets.MonthEnd(1)
    return pd.date_range(first, periods=months, freq="ME")


def _stable_hash(payload: object) -> str:
    def normalize(value: object) -> object:
        if isinstance(value, (date, datetime, pd.Timestamp, np.datetime64)):
            return pd.Timestamp(value).isoformat()
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, tuple):
            return [normalize(item) for item in value]
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): normalize(item) for key, item in value.items()}
        return value

    serialized = json.dumps(
        normalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True)
class AssetForecastConfig:
    """Immutable horizon, support, seed, and conservation configuration."""

    horizons: tuple[int, ...] = HORIZONS
    forecast_months: int = 12
    seed: int = 0
    min_effective_samples: int = 24
    conservation_tolerance: float = 1e-10
    model_version: str = "asset-forecast-v1"

    def __post_init__(self) -> None:
        horizons = tuple(
            sorted(
                {_positive_integer(value, name="horizon") for value in self.horizons}
            )
        )
        if horizons != HORIZONS:
            raise ValueError("horizons must be exactly 3, 6, and 12 months")
        months = _positive_integer(self.forecast_months, name="forecast_months")
        if months != 12:
            raise ValueError("forecast_months must be exactly 12")
        object.__setattr__(self, "horizons", horizons)
        object.__setattr__(self, "forecast_months", months)
        object.__setattr__(
            self,
            "seed",
            _nonnegative_integer(self.seed, name="seed"),
        )
        object.__setattr__(
            self,
            "min_effective_samples",
            _positive_integer(
                self.min_effective_samples,
                name="min_effective_samples",
            ),
        )
        object.__setattr__(
            self,
            "conservation_tolerance",
            _positive_real(
                self.conservation_tolerance,
                name="conservation_tolerance",
            ),
        )
        object.__setattr__(
            self,
            "model_version",
            _text(self.model_version, name="model_version"),
        )


def _config_hash(config: AssetForecastConfig) -> str:
    return _stable_hash(asdict(config))


def _rebuild_channel_forecast(value: object) -> ChannelForecastResult:
    if not isinstance(value, ChannelForecastResult):
        raise TypeError("channel_forecast must be a ChannelForecastResult")
    try:
        return ChannelForecastResult(
            summary=value.summary,
            draws=value.draws,
            covariance=value.covariance,
            evaluation=value.evaluation,
            forecast_input=value.forecast_input,
            config=value.config,
        )
    except ValueError as error:
        raise ValueError(
            "channel forecast is inconsistent with retained deterministic inputs"
        ) from error


def _rebuild_stage2(value: object) -> ChannelToAssetResult:
    if not isinstance(value, ChannelToAssetResult):
        raise TypeError("stage2 must be a ChannelToAssetResult")
    try:
        return ChannelToAssetResult(
            components=value.components,
            posteriors=value.posteriors,
            covariance=value.covariance,
        )
    except ValueError as error:
        raise ValueError(
            "stage2 result is inconsistent with its governed frames"
        ) from error


def _normalize_draw_ids(values: pd.Series, *, name: str) -> pd.Series:
    normalized = [_nonnegative_integer(value, name=name) for value in values.tolist()]
    return pd.Series(normalized, index=values.index, dtype="int64")


def _normalize_numeric(values: pd.Series, *, name: str) -> pd.Series:
    normalized = [_finite_real(value, name=name) for value in values.tolist()]
    return pd.Series(normalized, index=values.index, dtype="float64")


def _normalize_input_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
    value_column: str,
    has_component: bool,
    as_of: pd.Timestamp,
    forecast_dates: pd.DatetimeIndex,
    draw_count: int,
    asset_ids: set[str],
) -> pd.DataFrame:
    frame = _required_frame(values, name=name, columns=columns)
    for column in (
        "forecast_origin",
        "date",
        "visible_date",
        "generated_date",
        "data_vintage",
    ):
        frame[column] = _normalize_dates(frame[column], name=f"{name} {column}")
    for column in ("asset_id", "unit", "path_kind", "model_version"):
        frame[column] = [
            _text(value, name=f"{name} {column}") for value in frame[column].tolist()
        ]
    if has_component:
        frame["component_id"] = [
            _text(value, name=f"{name} component_id")
            for value in frame["component_id"].tolist()
        ]
    frame["draw_id"] = _normalize_draw_ids(
        frame["draw_id"],
        name=f"{name} draw_id",
    )
    frame[value_column] = _normalize_numeric(
        frame[value_column],
        name=f"{name} {value_column}",
    )
    if frame.empty:
        return frame
    if set(frame["forecast_origin"]) != {as_of}:
        raise ValueError(f"{name} forecast_origin must equal as_of")
    if not set(frame["date"]).issubset(set(forecast_dates)):
        raise ValueError(f"{name} dates must stay inside the future forecast horizon")
    if bool((frame["date"] <= as_of).any()):
        raise ValueError(
            f"{name} cannot mix historical actual and future forecast rows"
        )
    for column in ("visible_date", "generated_date", "data_vintage"):
        if bool((frame[column] > as_of).any()):
            raise ValueError(f"{name} {column} cannot follow as_of")
    if bool((frame["visible_date"] > frame["generated_date"]).any()):
        raise ValueError(f"{name} visible_date cannot follow generated_date")
    if bool((frame["data_vintage"] > frame["generated_date"]).any()):
        raise ValueError(f"{name} data_vintage cannot follow generated_date")
    if set(frame["path_kind"]) != {"forecast"}:
        raise ValueError(f"{name} path_kind must be forecast and cannot contain actual")
    if not set(frame["draw_id"]).issubset(set(range(draw_count))):
        raise ValueError(f"{name} draw_id is outside the governed channel draw range")
    if not set(frame["asset_id"]).issubset(asset_ids):
        raise ValueError(f"{name} contains assets outside the stage2 result")
    dimensions = ["date", "draw_id", "asset_id"]
    if has_component:
        dimensions.append("component_id")
    if frame.duplicated(dimensions).any():
        raise ValueError(f"{name} contains duplicate forecast dimensions")
    grouping = ["asset_id"] + (["component_id"] if has_component else [])
    if bool(frame.groupby(grouping, sort=False)["unit"].nunique().gt(1).any()):
        raise ValueError(f"{name} unit must be constant within each forecast surface")
    if name in {"benchmark_forecasts", "residual_forecasts"} and set(frame["unit"]) != {
        "decimal_return"
    }:
        raise ValueError(f"{name} unit must be decimal_return")
    if name == "benchmark_forecasts" and bool((frame[value_column] <= -1.0).any()):
        raise ValueError("benchmark monthly returns must be greater than -1 (-100%)")
    sort_columns = ["asset_id"]
    if has_component:
        sort_columns.append("component_id")
    sort_columns.extend(["draw_id", "date"])
    return frame.sort_values(sort_columns, kind="stable").reset_index(drop=True)


def _validate_stage2_dates(
    stage2: ChannelToAssetResult, *, as_of: pd.Timestamp
) -> None:
    for frame_name in ("components", "posteriors", "covariance"):
        frame = getattr(stage2, frame_name)
        dates = _normalize_dates(frame["date"], name=f"stage2 {frame_name} date")
        if bool((dates > as_of).any()):
            raise ValueError("future stage2 posterior rows cannot follow as_of")


def _validate_supplied_component_types(
    *,
    stage2: ChannelToAssetResult,
    valuation: pd.DataFrame,
    positioning: pd.DataFrame,
    controls: pd.DataFrame,
    interactions: pd.DataFrame,
    events: pd.DataFrame,
) -> None:
    posterior = stage2.posteriors
    asset_rows = posterior.loc[posterior["node_level"].eq("asset")]
    required = set(
        zip(
            asset_rows["node_id"],
            asset_rows["component_type"],
            asset_rows["component_id"],
            strict=True,
        )
    )
    supplied_groups = (
        (valuation, "control"),
        (positioning, "control"),
        (controls, "control"),
        (interactions, "interaction"),
        (events, "event"),
    )
    control_sources: list[set[tuple[str, str]]] = []
    for frame, component_type in supplied_groups:
        supplied = set(zip(frame["asset_id"], frame["component_id"], strict=True))
        if component_type == "control":
            control_sources.append(supplied)
        unknown = {
            (asset_id, component_id)
            for asset_id, component_id in supplied
            if (asset_id, component_type, component_id) not in required
        }
        if unknown:
            details = ", ".join(
                f"{asset}/{component}" for asset, component in sorted(unknown)
            )
            raise ValueError(f"explicit forecast inputs do not match stage2: {details}")
    overlap = (
        (control_sources[0] & control_sources[1])
        | (control_sources[0] & control_sources[2])
        | (control_sources[1] & control_sources[2])
    )
    if overlap:
        raise ValueError(
            "control components cannot appear in multiple explicit sources"
        )


def _frame_hash(frame: pd.DataFrame) -> str:
    try:
        values = pd.util.hash_pandas_object(frame, index=True).to_numpy(
            dtype="uint64",
            copy=False,
        )
    except TypeError:
        normalized = frame.map(
            lambda value: repr(value)
            if isinstance(value, (list, dict, set, np.ndarray))
            else value
        )
        values = pd.util.hash_pandas_object(normalized, index=True).to_numpy(
            dtype="uint64",
            copy=False,
        )
    digest = hashlib.sha256()
    digest.update("\x1f".join(str(column) for column in frame.columns).encode())
    digest.update("\x1f".join(str(dtype) for dtype in frame.dtypes).encode())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _channel_signature(result: ChannelForecastResult) -> dict[str, object]:
    forecast_input = object.__getattribute__(result, "forecast_input")
    cycle_result = object.__getattribute__(forecast_input, "cycle_forecast")
    cycle_input = object.__getattribute__(cycle_result, "forecast_input")
    return {
        "as_of": forecast_input.as_of,
        "summary": _frame_hash(object.__getattribute__(result, "summary")),
        "draws": _frame_hash(object.__getattribute__(result, "draws")),
        "covariance": _frame_hash(object.__getattribute__(result, "covariance")),
        "evaluation": _frame_hash(object.__getattribute__(result, "evaluation")),
        "config": asdict(object.__getattribute__(result, "config")),
        "channel_history": _frame_hash(
            object.__getattribute__(forecast_input, "channel_history")
        ),
        "cycle_predictor_archive": _frame_hash(
            object.__getattribute__(forecast_input, "cycle_predictor_archive")
        ),
        "exogenous_forecast_archive": _frame_hash(
            object.__getattribute__(forecast_input, "exogenous_forecast_archive")
        ),
        "current_channel_states": _frame_hash(
            object.__getattribute__(forecast_input, "current_channel_states")
        ),
        "current_exogenous_paths": _frame_hash(
            object.__getattribute__(forecast_input, "current_exogenous_paths")
        ),
        "channel_specs": [
            spec.model_dump(mode="json")
            for spec in object.__getattribute__(forecast_input, "channel_specs")
        ],
        "exogenous_feature_ids": list(
            object.__getattribute__(forecast_input, "exogenous_feature_ids")
        ),
        "cycle_summary": _frame_hash(object.__getattribute__(cycle_result, "summary")),
        "cycle_paths": _frame_hash(
            object.__getattribute__(cycle_result, "monthly_paths")
        ),
        "cycle_config": asdict(object.__getattribute__(cycle_result, "config")),
        "cycle_as_of": cycle_input.as_of,
        "cycle_specs": [
            spec.model_dump(mode="json")
            for spec in object.__getattribute__(cycle_input, "cycle_specs")
        ],
        "indicator_specs": [
            spec.model_dump(mode="json")
            for spec in object.__getattribute__(cycle_input, "indicator_specs")
        ],
        "cycle_states": _frame_hash(object.__getattribute__(cycle_input, "states")),
        "cycle_leading_signals": _frame_hash(
            object.__getattribute__(cycle_input, "leading_signals")
        ),
        "cycle_calibration_history": _frame_hash(
            object.__getattribute__(cycle_input, "calibration_history")
        ),
    }


def _asset_input_integrity(value: AssetForecastInput) -> str:
    stage2 = object.__getattribute__(value, "stage2")
    return _stable_hash(
        {
            "as_of": object.__getattribute__(value, "as_of"),
            "view_mode": object.__getattribute__(value, "view_mode"),
            "scenario_id": object.__getattribute__(value, "scenario_id"),
            "scenario_catalog_hash": object.__getattribute__(
                value,
                "scenario_catalog",
            ).config_hash,
            "channel": _channel_signature(
                object.__getattribute__(value, "channel_forecast")
            ),
            "stage2": {
                "components": _frame_hash(
                    object.__getattribute__(stage2, "components")
                ),
                "posteriors": _frame_hash(
                    object.__getattribute__(stage2, "posteriors")
                ),
                "covariance": _frame_hash(
                    object.__getattribute__(stage2, "covariance")
                ),
            },
            "forecast_frames": {
                field_name: _frame_hash(object.__getattribute__(value, field_name))
                for field_name in sorted(_INPUT_FRAME_FIELDS)
            },
        }
    )


@dataclass(frozen=True)
class AssetForecastInput:
    """Explicit point-in-time inputs for one governed future scenario view."""

    as_of: date
    view_mode: str
    scenario_catalog: ScenarioCatalog
    scenario_id: str
    channel_forecast: ChannelForecastResult
    stage2: ChannelToAssetResult
    valuation_forecasts: pd.DataFrame
    positioning_forecasts: pd.DataFrame
    control_forecasts: pd.DataFrame
    interaction_forecasts: pd.DataFrame
    event_forecasts: pd.DataFrame
    benchmark_forecasts: pd.DataFrame
    residual_forecasts: pd.DataFrame
    _integrity_hash: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        as_of = _normalize_date(self.as_of, name="as_of")
        view_mode = _text(self.view_mode, name="view_mode")
        if view_mode != "forecast":
            raise ValueError(
                "view_mode must be forecast; actual and forecast cannot share a view"
            )
        if not isinstance(self.scenario_catalog, ScenarioCatalog):
            raise TypeError("scenario_catalog must be a ScenarioCatalog")
        validate_standard_scenario_catalog(self.scenario_catalog)
        scenario_id = _text(self.scenario_id, name="scenario_id")
        try:
            self.scenario_catalog.get(scenario_id)
        except KeyError as error:
            raise ValueError(f"unknown scenario_id: {scenario_id}") from error
        channel_forecast = _rebuild_channel_forecast(self.channel_forecast)
        if pd.Timestamp(channel_forecast.forecast_input.as_of) != as_of:
            raise ValueError("channel forecast as_of must equal asset forecast as_of")
        stage2 = _rebuild_stage2(self.stage2)
        _validate_stage2_dates(stage2, as_of=as_of)
        asset_rows = stage2.posteriors.loc[stage2.posteriors["node_level"].eq("asset")]
        asset_ids = set(asset_rows["node_id"])
        if not asset_ids:
            raise ValueError("stage2 must retain at least one asset posterior")
        draw_count = channel_forecast.forecast_input.cycle_forecast.config.draw_count
        forecast_dates = _future_dates(as_of.date(), 12)
        normalized: dict[str, pd.DataFrame] = {}
        for field_name, (columns, value_column, has_component) in _FRAME_SPECS.items():
            normalized[field_name] = _normalize_input_frame(
                object.__getattribute__(self, field_name),
                name=field_name,
                columns=columns,
                value_column=value_column,
                has_component=has_component,
                as_of=as_of,
                forecast_dates=forecast_dates,
                draw_count=draw_count,
                asset_ids=asset_ids,
            )
        _validate_supplied_component_types(
            stage2=stage2,
            valuation=normalized["valuation_forecasts"],
            positioning=normalized["positioning_forecasts"],
            controls=normalized["control_forecasts"],
            interactions=normalized["interaction_forecasts"],
            events=normalized["event_forecasts"],
        )
        channel_ids = tuple(sorted(set(channel_forecast.draws["channel_id"])))
        resolve_scenario_shocks(
            self.scenario_catalog,
            scenario_id=scenario_id,
            forecast_dates=forecast_dates,
            channel_ids=channel_ids,
        )
        object.__setattr__(self, "as_of", as_of.date())
        object.__setattr__(self, "view_mode", view_mode)
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "channel_forecast", channel_forecast)
        object.__setattr__(self, "stage2", stage2)
        for field_name, frame in normalized.items():
            object.__setattr__(self, field_name, frame.copy(deep=True))
        object.__setattr__(self, "_integrity_hash", _asset_input_integrity(self))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _INPUT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value


def _rebuild_asset_input(value: object) -> AssetForecastInput:
    if not isinstance(value, AssetForecastInput):
        raise TypeError("forecast_input must be an AssetForecastInput")
    try:
        retained_hash = object.__getattribute__(value, "_integrity_hash")
    except AttributeError as error:
        raise ValueError(
            "forecast_input was not constructed by AssetForecastInput"
        ) from error
    if retained_hash != _asset_input_integrity(value):
        raise ValueError("forecast_input is inconsistent with its retained inputs")
    return value


@dataclass(frozen=True)
class _AssetPosterior:
    asset_id: str
    posterior_date: pd.Timestamp
    labels: tuple[tuple[str, str], ...]
    mean: np.ndarray | None
    covariance: np.ndarray | None
    status: str
    effective_training_count: int
    estimation_method: str

    @property
    def usable(self) -> bool:
        return self.status in _USABLE_STAGE2_STATUSES


@dataclass(frozen=True)
class _AssetSupport:
    available: bool
    reason: str | None
    effective_samples: int
    stage2_effective_training_count: int
    channel_training_count: int


@dataclass(frozen=True)
class _AssetProvenance:
    channel_forecast_model_version: str
    channel_forecast_config_hash: str
    channel_registry_hash: str
    cycle_forecast_model_version: str
    cycle_forecast_config_hash: str
    cycle_registry_hash: str
    stage2_estimation_method: str
    data_vintage: date
    feature_visible_date: object
    feature_generated_date: object
    feature_vintage_date: object
    model_provenance: str
    data_provenance: str


def _matrix_sqrt(values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values, dtype="float64")
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("coefficient covariance must be square")
    if not np.isfinite(matrix).all():
        raise ValueError("coefficient covariance must be finite")
    symmetric = (matrix + matrix.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    if float(eigenvalues.min()) < -1e-10 * scale:
        raise ValueError("coefficient covariance must be positive semidefinite")
    return (
        eigenvectors
        @ np.diag(np.sqrt(np.clip(eigenvalues, 0.0, None)))
        @ eigenvectors.T
    )


def _long_covariance(
    frame: pd.DataFrame,
    labels: tuple[tuple[str, str], ...],
) -> np.ndarray:
    lookup = {
        (
            (row.component_i_type, row.component_i_id),
            (row.component_j_type, row.component_j_id),
        ): row.coefficient_covariance
        for row in frame.itertuples(index=False)
    }
    expected = {(left, right) for left in labels for right in labels}
    if set(lookup) != expected:
        raise ValueError("stage2 covariance pairs do not align with posterior")
    matrix = np.asarray(
        [[lookup[(left, right)] for right in labels] for left in labels],
        dtype="float64",
    )
    _matrix_sqrt(matrix)
    return matrix


def _select_stage2(
    forecast_input: AssetForecastInput,
) -> dict[str, _AssetPosterior]:
    as_of = pd.Timestamp(forecast_input.as_of)
    stage2 = object.__getattribute__(forecast_input, "stage2")
    components = stage2.components
    posteriors = stage2.posteriors
    covariance = stage2.covariance
    for frame in (components, posteriors, covariance):
        frame["date"] = _normalize_dates(frame["date"], name="stage2 date")
    asset_rows = posteriors.loc[posteriors["node_level"].eq("asset")].copy()
    selected: dict[str, _AssetPosterior] = {}
    for asset_id in sorted(set(asset_rows["node_id"])):
        available_dates = asset_rows.loc[
            asset_rows["node_id"].eq(asset_id) & asset_rows["date"].le(as_of),
            "date",
        ]
        if available_dates.empty:
            raise ValueError(f"stage2 has no visible posterior for {asset_id}")
        posterior_date = pd.Timestamp(available_dates.max())
        group = asset_rows.loc[
            asset_rows["node_id"].eq(asset_id) & asset_rows["date"].eq(posterior_date)
        ].copy()
        statuses = set(group["status"])
        if len(statuses) != 1:
            raise ValueError("stage2 status cannot vary within an asset posterior")
        status = str(group["status"].iloc[0])
        labels = tuple(
            sorted(
                zip(group["component_type"], group["component_id"], strict=True),
                key=lambda item: (_COMPONENT_ORDER.get(item[0], 99), item[1]),
            )
        )
        if len(labels) != len(set(labels)):
            raise ValueError("stage2 posterior components must be unique")
        if sum(component_type == "intercept" for component_type, _ in labels) != 1:
            raise ValueError("stage2 posterior requires exactly one intercept")
        if not any(component_type == "channel" for component_type, _ in labels):
            raise ValueError("stage2 posterior requires at least one channel")
        methods = set(group["estimation_method"])
        if len(methods) != 1:
            raise ValueError("stage2 estimation_method must be constant")
        effective_count = min(
            _nonnegative_floor(
                value,
                name="stage2 effective_training_count",
            )
            for value in group["effective_training_count"].tolist()
        )
        component_group = components.loc[
            components["asset_id"].eq(asset_id) & components["date"].eq(posterior_date)
        ]
        if component_group.empty:
            raise ValueError("stage2 components must align with posterior date")
        component_labels = set(
            zip(
                component_group.loc[
                    component_group["component_type"].ne("residual"),
                    "component_type",
                ],
                component_group.loc[
                    component_group["component_type"].ne("residual"),
                    "component_id",
                ],
                strict=True,
            )
        )
        if component_labels != set(labels):
            raise ValueError("stage2 components do not align with posterior labels")
        if status in _USABLE_STAGE2_STATUSES:
            indexed = group.set_index(["component_type", "component_id"])
            means = np.asarray(
                [
                    _finite_real(
                        indexed.loc[label, "coefficient_mean"],
                        name="stage2 coefficient_mean",
                    )
                    for label in labels
                ],
                dtype="float64",
            )
            component_indexed = component_group.set_index(
                ["component_type", "component_id"]
            )
            component_means = np.asarray(
                [component_indexed.loc[label, "coefficient_mean"] for label in labels],
                dtype="float64",
            )
            if not np.allclose(means, component_means, atol=1e-12, rtol=1e-12):
                raise ValueError(
                    "stage2 posterior coefficients are inconsistent with components"
                )
            covariance_group = covariance.loc[
                covariance["node_level"].eq("asset")
                & covariance["node_id"].eq(asset_id)
                & covariance["date"].eq(posterior_date)
            ]
            matrix = _long_covariance(covariance_group, labels)
        else:
            means = None
            matrix = None
        selected[asset_id] = _AssetPosterior(
            asset_id=asset_id,
            posterior_date=posterior_date,
            labels=labels,
            mean=means,
            covariance=matrix,
            status=status,
            effective_training_count=effective_count,
            estimation_method=str(next(iter(methods))),
        )
    return selected


def _surface_keys(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    component_id: str | None,
) -> set[tuple[int, pd.Timestamp]]:
    group = frame.loc[frame["asset_id"].eq(asset_id)]
    if component_id is not None:
        group = group.loc[group["component_id"].eq(component_id)]
    return set(zip(group["draw_id"], group["date"], strict=True))


def _complete_surface(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    component_id: str | None,
    draw_count: int,
    forecast_dates: pd.DatetimeIndex,
) -> bool:
    expected = {
        (draw_id, pd.Timestamp(forecast_date))
        for draw_id in range(draw_count)
        for forecast_date in forecast_dates
    }
    return (
        _surface_keys(
            frame,
            asset_id=asset_id,
            component_id=component_id,
        )
        == expected
    )


def _control_source_map(
    forecast_input: AssetForecastInput,
) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for field_name, source in (
        ("valuation_forecasts", "valuation"),
        ("positioning_forecasts", "positioning"),
        ("control_forecasts", "control"),
    ):
        frame = object.__getattribute__(forecast_input, field_name)
        for key in set(zip(frame["asset_id"], frame["component_id"], strict=True)):
            mapping[key] = source
    return mapping


def _channel_support(
    forecast_input: AssetForecastInput,
    *,
    channel_ids: set[str],
    forecast_months: int,
) -> tuple[bool, int]:
    if not channel_ids:
        return False, 0
    summary = forecast_input.channel_forecast.summary
    selected = summary.loc[
        summary["channel_id"].isin(channel_ids)
        & summary["horizon_months"].isin(range(1, forecast_months + 1))
    ]
    expected_count = len(channel_ids) * forecast_months
    if len(selected) != expected_count or set(selected["status"]) != {"available"}:
        return False, 0
    counts = [
        _nonnegative_integer(value, name="channel training_count")
        for value in selected["training_count"].tolist()
    ]
    return True, min(counts)


def _asset_supports(
    forecast_input: AssetForecastInput,
    *,
    posteriors: Mapping[str, _AssetPosterior],
    config: AssetForecastConfig,
) -> dict[str, _AssetSupport]:
    draw_count = (
        forecast_input.channel_forecast.forecast_input.cycle_forecast.config.draw_count
    )
    dates = _future_dates(forecast_input.as_of, config.forecast_months)
    control_sources = _control_source_map(forecast_input)
    frame_by_source = {
        "valuation": object.__getattribute__(forecast_input, "valuation_forecasts"),
        "positioning": object.__getattribute__(
            forecast_input,
            "positioning_forecasts",
        ),
        "control": object.__getattribute__(forecast_input, "control_forecasts"),
    }
    interactions = object.__getattribute__(forecast_input, "interaction_forecasts")
    events = object.__getattribute__(forecast_input, "event_forecasts")
    benchmarks = object.__getattribute__(forecast_input, "benchmark_forecasts")
    residuals = object.__getattribute__(forecast_input, "residual_forecasts")
    supports: dict[str, _AssetSupport] = {}
    for asset_id, posterior in posteriors.items():
        reasons: list[str] = []
        channel_ids = {
            component_id
            for component_type, component_id in posterior.labels
            if component_type == "channel"
        }
        channels_available, channel_count = _channel_support(
            forecast_input,
            channel_ids=channel_ids,
            forecast_months=config.forecast_months,
        )
        if not posterior.usable:
            reasons.append(f"stage2_{posterior.status}")
        if not channels_available:
            reasons.append("channel_forecast_unavailable")
        for component_type, component_id in posterior.labels:
            if component_type == "control":
                source = control_sources.get((asset_id, component_id))
                if source is None or not _complete_surface(
                    frame_by_source[source],
                    asset_id=asset_id,
                    component_id=component_id,
                    draw_count=draw_count,
                    forecast_dates=dates,
                ):
                    reasons.append(f"missing_control_forecast:{component_id}")
            elif component_type == "interaction" and not _complete_surface(
                interactions,
                asset_id=asset_id,
                component_id=component_id,
                draw_count=draw_count,
                forecast_dates=dates,
            ):
                reasons.append(f"missing_interaction_forecast:{component_id}")
            elif component_type == "event" and not _complete_surface(
                events,
                asset_id=asset_id,
                component_id=component_id,
                draw_count=draw_count,
                forecast_dates=dates,
            ):
                reasons.append(f"missing_event_forecast:{component_id}")
        if not _complete_surface(
            benchmarks,
            asset_id=asset_id,
            component_id=None,
            draw_count=draw_count,
            forecast_dates=dates,
        ):
            reasons.append("missing_benchmark_forecast")
        if not _complete_surface(
            residuals,
            asset_id=asset_id,
            component_id=None,
            draw_count=draw_count,
            forecast_dates=dates,
        ):
            reasons.append("missing_residual_forecast")
        effective = min(posterior.effective_training_count, channel_count)
        if effective < config.min_effective_samples:
            reasons.append("low_effective_support")
        unique_reasons = tuple(dict.fromkeys(reasons))
        supports[asset_id] = _AssetSupport(
            available=not unique_reasons,
            reason=";".join(unique_reasons) if unique_reasons else None,
            effective_samples=effective,
            stage2_effective_training_count=posterior.effective_training_count,
            channel_training_count=channel_count,
        )
    return supports


def _rng(seed: int, *key: object) -> np.random.Generator:
    payload = "\x1f".join(str(value) for value in key).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=16).digest()
    entropy = [seed, *np.frombuffer(digest, dtype="uint32").tolist()]
    return np.random.default_rng(np.random.SeedSequence(entropy))


def _normal_draws(
    mean: np.ndarray,
    covariance: np.ndarray,
    *,
    draw_count: int,
    generator: np.random.Generator,
) -> np.ndarray:
    standard = generator.standard_normal((draw_count, len(mean)))
    return mean + standard @ _matrix_sqrt(covariance).T


def _frame_records(
    frame: pd.DataFrame,
    *,
    value_column: str,
    has_component: bool,
) -> dict[tuple[object, ...], dict[str, object]]:
    records: dict[tuple[object, ...], dict[str, object]] = {}
    for row in frame.to_dict(orient="records"):
        key: tuple[object, ...]
        if has_component:
            key = (
                row["asset_id"],
                row["component_id"],
                int(row["draw_id"]),
                pd.Timestamp(row["date"]),
            )
        else:
            key = (
                row["asset_id"],
                int(row["draw_id"]),
                pd.Timestamp(row["date"]),
            )
        row["value"] = float(row[value_column])
        records[key] = row
    return records


def _asset_feature_frames(
    forecast_input: AssetForecastInput,
    *,
    posterior: _AssetPosterior,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for field_name in ("benchmark_forecasts", "residual_forecasts"):
        frame = object.__getattribute__(forecast_input, field_name)
        frames[field_name] = frame.loc[frame["asset_id"].eq(posterior.asset_id)].copy()
    control_sources = _control_source_map(forecast_input)
    source_fields = {
        "valuation": "valuation_forecasts",
        "positioning": "positioning_forecasts",
        "control": "control_forecasts",
        "interaction": "interaction_forecasts",
        "event": "event_forecasts",
    }
    for component_type, component_id in posterior.labels:
        if component_type == "control":
            source = control_sources.get((posterior.asset_id, component_id))
            if source is None:
                continue
        elif component_type in {"interaction", "event"}:
            source = component_type
        else:
            continue
        field_name = source_fields[source]
        frame = object.__getattribute__(forecast_input, field_name)
        frames[f"{field_name}:{component_id}"] = frame.loc[
            frame["asset_id"].eq(posterior.asset_id)
            & frame["component_id"].eq(component_id)
        ].copy()
    return frames


def _optional_feature_date(
    frames: Mapping[str, pd.DataFrame],
    *,
    column: str,
) -> object:
    values = [
        pd.Timestamp(frame[column].max())
        for frame in frames.values()
        if not frame.empty
    ]
    if not values:
        return pd.NaT
    return max(values).date()


def _date_iso(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _asset_provenance(
    forecast_input: AssetForecastInput,
    *,
    config: AssetForecastConfig,
    posterior: _AssetPosterior,
) -> _AssetProvenance:
    channel = forecast_input.channel_forecast.draws
    channel_ids = {
        component_id
        for component_type, component_id in posterior.labels
        if component_type == "channel"
    }
    channel_evidence = channel.loc[
        channel["channel_id"].isin(channel_ids)
        & channel["horizon_months"].isin(range(1, config.forecast_months + 1))
    ]
    feature_frames = _asset_feature_frames(
        forecast_input,
        posterior=posterior,
    )
    feature_models = sorted(
        {
            str(value)
            for frame in feature_frames.values()
            for value in frame["model_version"].tolist()
        }
    )
    feature_visible_date = _optional_feature_date(
        feature_frames,
        column="visible_date",
    )
    feature_generated_date = _optional_feature_date(
        feature_frames,
        column="generated_date",
    )
    feature_vintage_date = _optional_feature_date(
        feature_frames,
        column="data_vintage",
    )
    evidence_dates = [posterior.posterior_date.date()]
    if not channel_evidence.empty:
        channel_vintages = _normalize_dates(
            channel_evidence["data_vintage"],
            name="channel data_vintage",
        )
        evidence_dates.append(channel_vintages.max().date())
    if not pd.isna(feature_vintage_date):
        evidence_dates.append(pd.Timestamp(feature_vintage_date).date())
    data_vintage = max(evidence_dates)
    channel_model = str(_constant(channel, "forecast_model_version"))
    channel_config_hash = str(_constant(channel, "forecast_config_hash"))
    channel_registry_hash = str(_constant(channel, "channel_registry_hash"))
    cycle_model = str(_constant(channel, "cycle_forecast_model_version"))
    cycle_config_hash = str(_constant(channel, "cycle_forecast_config_hash"))
    cycle_registry_hash = str(_constant(channel, "cycle_registry_hash"))
    model = json.dumps(
        {
            "asset_model_version": config.model_version,
            "channel_model_version": channel_model,
            "channel_config_hash": channel_config_hash,
            "cycle_model_version": cycle_model,
            "stage2_estimation_method": posterior.estimation_method,
            "feature_model_versions": feature_models,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    data = json.dumps(
        {
            "as_of": forecast_input.as_of.isoformat(),
            "stage2_posterior_date": posterior.posterior_date.date().isoformat(),
            "data_vintage": data_vintage.isoformat(),
            "feature_visible_date": _date_iso(feature_visible_date),
            "feature_generated_date": _date_iso(feature_generated_date),
            "feature_vintage_date": _date_iso(feature_vintage_date),
            "feature_input_hash": _stable_hash(
                {
                    name: _frame_hash(frame)
                    for name, frame in sorted(feature_frames.items())
                }
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _AssetProvenance(
        channel_forecast_model_version=channel_model,
        channel_forecast_config_hash=channel_config_hash,
        channel_registry_hash=channel_registry_hash,
        cycle_forecast_model_version=cycle_model,
        cycle_forecast_config_hash=cycle_config_hash,
        cycle_registry_hash=cycle_registry_hash,
        stage2_estimation_method=posterior.estimation_method,
        data_vintage=data_vintage,
        feature_visible_date=feature_visible_date,
        feature_generated_date=feature_generated_date,
        feature_vintage_date=feature_vintage_date,
        model_provenance=model,
        data_provenance=data,
    )


def _channel_paths(
    forecast_input: AssetForecastInput,
    *,
    config: AssetForecastConfig,
) -> pd.DataFrame:
    dates = _future_dates(forecast_input.as_of, config.forecast_months)
    channel_result = forecast_input.channel_forecast
    channel_draws = channel_result.draws.loc[
        channel_result.draws["horizon_months"].isin(
            range(1, config.forecast_months + 1)
        )
    ].copy()
    draw_count = channel_result.forecast_input.cycle_forecast.config.draw_count
    channel_ids = tuple(sorted(set(channel_draws["channel_id"])))
    expected = len(channel_ids) * draw_count * config.forecast_months
    if len(channel_draws) != expected:
        raise ValueError("channel forecast must retain continuous monthly draws")
    if set(channel_draws["draw_id"]) != set(range(draw_count)):
        raise ValueError("channel forecast draw ids must align exactly")
    if set(pd.to_datetime(channel_draws["forecast_date"])) != set(dates):
        raise ValueError("channel forecast dates must cover the next 12 month ends")
    shocks = resolve_scenario_shocks(
        forecast_input.scenario_catalog,
        scenario_id=forecast_input.scenario_id,
        forecast_dates=dates,
        channel_ids=channel_ids,
    )
    shock_lookup = {
        (row.channel_id, pd.Timestamp(row.date)): row
        for row in shocks.itertuples(index=False)
    }
    scenario = forecast_input.scenario_catalog.get(forecast_input.scenario_id)
    records = []
    for row in channel_draws.sort_values(
        ["channel_id", "draw_id", "horizon_months"],
        kind="stable",
    ).itertuples(index=False):
        forecast_date = pd.Timestamp(row.forecast_date)
        shock = shock_lookup[(row.channel_id, forecast_date)]
        if row.status == "available":
            origin_state = float(row.origin_state)
            baseline_state = float(row.forecast_state)
            baseline_innovation = float(row.forecast_innovation)
            if not np.isclose(
                baseline_state,
                origin_state + baseline_innovation,
                atol=config.conservation_tolerance,
                rtol=config.conservation_tolerance,
            ):
                raise ValueError(
                    "channel forecast state does not conserve origin plus innovation"
                )
            adjusted_innovation = baseline_innovation + float(shock.scenario_shock)
            adjusted_state = baseline_state + float(shock.scenario_shock)
        else:
            origin_state = np.nan
            baseline_state = np.nan
            baseline_innovation = np.nan
            adjusted_innovation = np.nan
            adjusted_state = np.nan
        records.append(
            {
                "scenario_id": scenario.scenario_id,
                "scenario_version": scenario.version,
                "catalog_version": forecast_input.scenario_catalog.catalog_version,
                "scenario_config_hash": forecast_input.scenario_catalog.config_hash,
                "channel_id": row.channel_id,
                "draw_id": int(row.draw_id),
                "month_number": int(row.horizon_months),
                "date": forecast_date,
                "forecast_origin": forecast_input.as_of,
                "status": row.status,
                "unavailable_reason": row.unavailable_reason,
                "origin_channel_state": origin_state,
                "baseline_channel_state": baseline_state,
                "baseline_channel_innovation": baseline_innovation,
                "scenario_shock": float(shock.scenario_shock),
                "adjusted_channel_innovation": adjusted_innovation,
                "adjusted_channel_state": adjusted_state,
                "shock_id": shock.shock_id,
                "shock_version": shock.shock_version,
                "shock_unit": shock.unit,
                "shock_direction": shock.direction,
                "shock_path": shock.path,
                "channel_forecast_model_version": row.forecast_model_version,
                "channel_forecast_config_hash": row.forecast_config_hash,
                "channel_registry_hash": row.channel_registry_hash,
                "cycle_forecast_model_version": row.cycle_forecast_model_version,
                "cycle_forecast_config_hash": row.cycle_forecast_config_hash,
                "cycle_registry_hash": row.cycle_registry_hash,
                "data_vintage": row.data_vintage,
            }
        )
    return (
        pd.DataFrame(records, columns=SCENARIO_CHANNEL_PATH_COLUMNS)
        .sort_values(
            ["channel_id", "draw_id", "month_number"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _component_source(
    *,
    asset_id: str,
    component_type: str,
    component_id: str,
    control_sources: Mapping[tuple[str, str], str],
) -> str:
    if component_type == "control":
        source = control_sources.get((asset_id, component_id))
        if source is None:
            raise ValueError(
                f"missing explicit control source for {asset_id}/{component_id}"
            )
        return source
    return component_type


def _component_input(
    *,
    asset_id: str,
    draw_id: int,
    forecast_date: pd.Timestamp,
    component_type: str,
    component_id: str,
    source: str,
    channel_lookup: Mapping[tuple[str, int, int], Mapping[str, object]],
    explicit_lookups: Mapping[str, Mapping[tuple[object, ...], Mapping[str, object]]],
    benchmark_lookup: Mapping[tuple[object, ...], Mapping[str, object]],
    posterior_date: pd.Timestamp,
    as_of: date,
) -> tuple[float, float, date, date, date, str, str]:
    month_number = int(
        (forecast_date.year - as_of.year) * 12 + forecast_date.month - as_of.month
    )
    if component_type == "intercept":
        posterior = posterior_date.date()
        return 1.0, 0.0, posterior, posterior, posterior, "constant", "stage2"
    if component_type == "channel":
        row = channel_lookup[(component_id, draw_id, month_number)]
        data_vintage = pd.Timestamp(row["data_vintage"]).date()
        return (
            float(row["baseline_channel_innovation"]),
            float(row["scenario_shock"]),
            as_of,
            as_of,
            data_vintage,
            "channel_innovation",
            str(row["channel_forecast_model_version"]),
        )
    if component_type == "benchmark":
        row = benchmark_lookup[(asset_id, draw_id, forecast_date)]
    else:
        row = explicit_lookups[source][(asset_id, component_id, draw_id, forecast_date)]
    return (
        float(row["value"]),
        0.0,
        pd.Timestamp(row["visible_date"]).date(),
        pd.Timestamp(row["generated_date"]).date(),
        pd.Timestamp(row["data_vintage"]).date(),
        str(row["unit"]),
        str(row["model_version"]),
    )


def _components_and_monthly(
    forecast_input: AssetForecastInput,
    *,
    config: AssetForecastConfig,
    posteriors: Mapping[str, _AssetPosterior],
    supports: Mapping[str, _AssetSupport],
    provenance_by_asset: Mapping[str, _AssetProvenance],
    channel_paths: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    draw_count = (
        forecast_input.channel_forecast.forecast_input.cycle_forecast.config.draw_count
    )
    dates = _future_dates(forecast_input.as_of, config.forecast_months)
    config_hash = _config_hash(config)
    scenario = forecast_input.scenario_catalog.get(forecast_input.scenario_id)
    control_sources = _control_source_map(forecast_input)
    channel_lookup = {
        (row.channel_id, int(row.draw_id), int(row.month_number)): row._asdict()
        for row in channel_paths.itertuples(index=False)
    }
    explicit_lookups = {
        "valuation": _frame_records(
            object.__getattribute__(forecast_input, "valuation_forecasts"),
            value_column="valuation_value",
            has_component=True,
        ),
        "positioning": _frame_records(
            object.__getattribute__(forecast_input, "positioning_forecasts"),
            value_column="positioning_value",
            has_component=True,
        ),
        "control": _frame_records(
            object.__getattribute__(forecast_input, "control_forecasts"),
            value_column="control_value",
            has_component=True,
        ),
        "interaction": _frame_records(
            object.__getattribute__(forecast_input, "interaction_forecasts"),
            value_column="interaction_value",
            has_component=True,
        ),
        "event": _frame_records(
            object.__getattribute__(forecast_input, "event_forecasts"),
            value_column="event_value",
            has_component=True,
        ),
    }
    benchmark_lookup = _frame_records(
        object.__getattribute__(forecast_input, "benchmark_forecasts"),
        value_column="benchmark_return",
        has_component=False,
    )
    residual_lookup = _frame_records(
        object.__getattribute__(forecast_input, "residual_forecasts"),
        value_column="residual_return",
        has_component=False,
    )
    component_records: list[dict[str, object]] = []
    monthly_records: list[dict[str, object]] = []
    for asset_id, posterior in posteriors.items():
        if not supports[asset_id].available:
            continue
        if posterior.mean is None or posterior.covariance is None:
            raise ValueError("available asset requires a finite stage2 posterior")
        coefficients = _normal_draws(
            posterior.mean,
            posterior.covariance,
            draw_count=draw_count,
            generator=_rng(
                config.seed,
                forecast_input.as_of,
                asset_id,
                posterior.posterior_date,
                config.model_version,
            ),
        )
        provenance = provenance_by_asset[asset_id]
        for draw_id in range(draw_count):
            for month_number, forecast_date in enumerate(dates, start=1):
                rows: list[dict[str, object]] = []
                for position, (component_type, component_id) in enumerate(
                    posterior.labels
                ):
                    source = _component_source(
                        asset_id=asset_id,
                        component_type=component_type,
                        component_id=component_id,
                        control_sources=control_sources,
                    )
                    (
                        baseline_predictor,
                        scenario_predictor,
                        visible_date,
                        generated_date,
                        data_vintage,
                        unit,
                        input_model_version,
                    ) = _component_input(
                        asset_id=asset_id,
                        draw_id=draw_id,
                        forecast_date=pd.Timestamp(forecast_date),
                        component_type=component_type,
                        component_id=component_id,
                        source=source,
                        channel_lookup=channel_lookup,
                        explicit_lookups=explicit_lookups,
                        benchmark_lookup=benchmark_lookup,
                        posterior_date=posterior.posterior_date,
                        as_of=forecast_input.as_of,
                    )
                    coefficient = float(coefficients[draw_id, position])
                    baseline_contribution = coefficient * baseline_predictor
                    scenario_contribution = coefficient * scenario_predictor
                    rows.append(
                        {
                            "asset_id": asset_id,
                            "scenario_id": scenario.scenario_id,
                            "draw_id": draw_id,
                            "month_number": month_number,
                            "date": pd.Timestamp(forecast_date),
                            "forecast_origin": forecast_input.as_of,
                            "stage2_posterior_date": posterior.posterior_date.date(),
                            "status": "available",
                            "component_type": component_type,
                            "component_id": component_id,
                            "source_type": source,
                            "baseline_predictor_value": baseline_predictor,
                            "scenario_predictor_value": scenario_predictor,
                            "adjusted_predictor_value": (
                                baseline_predictor + scenario_predictor
                            ),
                            "coefficient_mean": float(posterior.mean[position]),
                            "coefficient_draw": coefficient,
                            "baseline_contribution": baseline_contribution,
                            "scenario_contribution": scenario_contribution,
                            "contribution": (
                                baseline_contribution + scenario_contribution
                            ),
                            "cycle_contribution": 0.0,
                            "visible_date": visible_date,
                            "generated_date": generated_date,
                            "data_vintage": data_vintage,
                            "unit": unit,
                            "input_model_version": input_model_version,
                            "scenario_version": scenario.version,
                            "catalog_version": (
                                forecast_input.scenario_catalog.catalog_version
                            ),
                            "scenario_config_hash": (
                                forecast_input.scenario_catalog.config_hash
                            ),
                            "asset_forecast_model_version": config.model_version,
                            "asset_forecast_config_hash": config_hash,
                        }
                    )
                residual = residual_lookup[
                    (asset_id, draw_id, pd.Timestamp(forecast_date))
                ]
                residual_value = float(residual["value"])
                rows.append(
                    {
                        "asset_id": asset_id,
                        "scenario_id": scenario.scenario_id,
                        "draw_id": draw_id,
                        "month_number": month_number,
                        "date": pd.Timestamp(forecast_date),
                        "forecast_origin": forecast_input.as_of,
                        "stage2_posterior_date": posterior.posterior_date.date(),
                        "status": "available",
                        "component_type": "residual",
                        "component_id": "asset_residual",
                        "source_type": "residual",
                        "baseline_predictor_value": residual_value,
                        "scenario_predictor_value": 0.0,
                        "adjusted_predictor_value": residual_value,
                        "coefficient_mean": 1.0,
                        "coefficient_draw": 1.0,
                        "baseline_contribution": residual_value,
                        "scenario_contribution": 0.0,
                        "contribution": residual_value,
                        "cycle_contribution": 0.0,
                        "visible_date": pd.Timestamp(residual["visible_date"]).date(),
                        "generated_date": pd.Timestamp(
                            residual["generated_date"]
                        ).date(),
                        "data_vintage": pd.Timestamp(residual["data_vintage"]).date(),
                        "unit": residual["unit"],
                        "input_model_version": residual["model_version"],
                        "scenario_version": scenario.version,
                        "catalog_version": forecast_input.scenario_catalog.catalog_version,
                        "scenario_config_hash": forecast_input.scenario_catalog.config_hash,
                        "asset_forecast_model_version": config.model_version,
                        "asset_forecast_config_hash": config_hash,
                    }
                )
                component_records.extend(rows)
                baseline_total = float(
                    sum(float(row["baseline_contribution"]) for row in rows)
                )
                scenario_total = float(
                    sum(float(row["scenario_contribution"]) for row in rows)
                )
                asset_return = float(sum(float(row["contribution"]) for row in rows))
                if not np.isclose(
                    asset_return,
                    baseline_total + scenario_total,
                    atol=config.conservation_tolerance,
                    rtol=config.conservation_tolerance,
                ):
                    raise ValueError("monthly asset contributions do not conserve")
                benchmark_return = float(
                    benchmark_lookup[(asset_id, draw_id, pd.Timestamp(forecast_date))][
                        "value"
                    ]
                )
                if asset_return <= -1.0 or baseline_total <= -1.0:
                    raise ValueError(
                        "asset monthly returns must be greater than -1 (-100%)"
                    )
                if benchmark_return <= -1.0:
                    raise ValueError(
                        "benchmark monthly returns must be greater than -1 (-100%)"
                    )
                relative_return = (1.0 + asset_return) / (1.0 + benchmark_return) - 1.0
                sums = {
                    source: float(
                        sum(
                            float(row["baseline_contribution"])
                            for row in rows
                            if row["source_type"] == source
                        )
                    )
                    for source in _SOURCE_ORDER
                }
                decomposition_total = sum(sums.values()) + scenario_total
                if not np.isclose(
                    decomposition_total,
                    asset_return,
                    atol=config.conservation_tolerance,
                    rtol=config.conservation_tolerance,
                ):
                    raise ValueError("monthly decomposition does not conserve")
                monthly_records.append(
                    {
                        "asset_id": asset_id,
                        "scenario_id": scenario.scenario_id,
                        "draw_id": draw_id,
                        "month_number": month_number,
                        "date": pd.Timestamp(forecast_date),
                        "forecast_origin": forecast_input.as_of,
                        "stage2_posterior_date": posterior.posterior_date.date(),
                        "baseline_asset_monthly_return": baseline_total,
                        "asset_monthly_return": asset_return,
                        "benchmark_monthly_return": benchmark_return,
                        "relative_monthly_return": relative_return,
                        "intercept_contribution": sums["intercept"],
                        "benchmark_contribution": sums["benchmark"],
                        "channel_contribution": sums["channel"],
                        "valuation_contribution": sums["valuation"],
                        "positioning_contribution": sums["positioning"],
                        "control_contribution": sums["control"],
                        "interaction_contribution": sums["interaction"],
                        "event_contribution": sums["event"],
                        "scenario_contribution": scenario_total,
                        "residual_contribution": sums["residual"],
                        "cycle_contribution": 0.0,
                        "status": "available",
                        "scenario_version": scenario.version,
                        "catalog_version": forecast_input.scenario_catalog.catalog_version,
                        "scenario_config_hash": forecast_input.scenario_catalog.config_hash,
                        "asset_forecast_model_version": config.model_version,
                        "asset_forecast_config_hash": config_hash,
                        "channel_forecast_model_version": (
                            provenance.channel_forecast_model_version
                        ),
                        "channel_forecast_config_hash": (
                            provenance.channel_forecast_config_hash
                        ),
                        "channel_registry_hash": provenance.channel_registry_hash,
                        "cycle_forecast_model_version": (
                            provenance.cycle_forecast_model_version
                        ),
                        "cycle_forecast_config_hash": (
                            provenance.cycle_forecast_config_hash
                        ),
                        "cycle_registry_hash": provenance.cycle_registry_hash,
                        "stage2_estimation_method": (
                            provenance.stage2_estimation_method
                        ),
                        "data_vintage": provenance.data_vintage,
                        "feature_visible_date": provenance.feature_visible_date,
                        "feature_generated_date": provenance.feature_generated_date,
                        "feature_vintage_date": provenance.feature_vintage_date,
                        "model_provenance": provenance.model_provenance,
                        "data_provenance": provenance.data_provenance,
                    }
                )
    components = pd.DataFrame(
        component_records,
        columns=ASSET_FORECAST_COMPONENT_COLUMNS,
    )
    monthly = pd.DataFrame(monthly_records, columns=ASSET_FORECAST_MONTHLY_COLUMNS)
    if not components.empty:
        components["_source_order"] = components["source_type"].map(_SOURCE_ORDER)
        components = (
            components.sort_values(
                [
                    "asset_id",
                    "draw_id",
                    "month_number",
                    "_source_order",
                    "component_id",
                ],
                kind="stable",
            )
            .drop(columns="_source_order")
            .reset_index(drop=True)
        )
    if not monthly.empty:
        monthly = monthly.sort_values(
            ["asset_id", "draw_id", "month_number"],
            kind="stable",
        ).reset_index(drop=True)
    return components, monthly


def _compound(values: np.ndarray) -> np.ndarray:
    if bool((values <= -1.0).any()):
        raise ValueError("monthly returns must be greater than -1 (-100%)")
    compounded = np.expm1(np.sum(np.log1p(values), axis=1))
    if not np.isfinite(compounded).all():
        raise ValueError("compounded returns must remain finite")
    return compounded


def _horizon_draws(
    monthly: pd.DataFrame,
    *,
    forecast_input: AssetForecastInput,
    config: AssetForecastConfig,
    provenance_by_asset: Mapping[str, _AssetProvenance],
) -> pd.DataFrame:
    records = []
    scenario = forecast_input.scenario_catalog.get(forecast_input.scenario_id)
    config_hash = _config_hash(config)
    for (asset_id, draw_id), group in monthly.groupby(
        ["asset_id", "draw_id"],
        sort=True,
    ):
        provenance = provenance_by_asset[str(asset_id)]
        ordered = group.sort_values("month_number", kind="stable")
        if list(ordered["month_number"]) != list(range(1, config.forecast_months + 1)):
            raise ValueError("monthly asset draws must cover one shared 12-month path")
        for horizon in config.horizons:
            prefix = ordered.iloc[:horizon]
            asset_values = prefix["asset_monthly_return"].to_numpy(dtype="float64")
            baseline_values = prefix["baseline_asset_monthly_return"].to_numpy(
                dtype="float64"
            )
            benchmark_values = prefix["benchmark_monthly_return"].to_numpy(
                dtype="float64"
            )
            relative_values = prefix["relative_monthly_return"].to_numpy(
                dtype="float64"
            )
            absolute = float(_compound(asset_values[np.newaxis, :])[0])
            baseline = float(_compound(baseline_values[np.newaxis, :])[0])
            benchmark = float(_compound(benchmark_values[np.newaxis, :])[0])
            excess = (1.0 + absolute) / (1.0 + benchmark) - 1.0
            records.append(
                {
                    "asset_id": asset_id,
                    "scenario_id": scenario.scenario_id,
                    "draw_id": int(draw_id),
                    "horizon_months": horizon,
                    "forecast_origin": forecast_input.as_of,
                    "stage2_posterior_date": ordered["stage2_posterior_date"].iloc[0],
                    "absolute_return": absolute,
                    "baseline_absolute_return": baseline,
                    "scenario_return_effect": absolute - baseline,
                    "benchmark_return": benchmark,
                    "excess_return": excess,
                    "absolute_max_drawdown": float(compute_max_drawdown(asset_values)),
                    "excess_max_drawdown": float(compute_max_drawdown(relative_values)),
                    "status": "available",
                    "scenario_version": scenario.version,
                    "catalog_version": forecast_input.scenario_catalog.catalog_version,
                    "scenario_config_hash": forecast_input.scenario_catalog.config_hash,
                    "asset_forecast_model_version": config.model_version,
                    "asset_forecast_config_hash": config_hash,
                    "channel_forecast_model_version": (
                        provenance.channel_forecast_model_version
                    ),
                    "channel_forecast_config_hash": (
                        provenance.channel_forecast_config_hash
                    ),
                    "channel_registry_hash": provenance.channel_registry_hash,
                    "cycle_forecast_model_version": (
                        provenance.cycle_forecast_model_version
                    ),
                    "cycle_forecast_config_hash": (
                        provenance.cycle_forecast_config_hash
                    ),
                    "cycle_registry_hash": provenance.cycle_registry_hash,
                    "stage2_estimation_method": (provenance.stage2_estimation_method),
                    "data_vintage": provenance.data_vintage,
                    "feature_visible_date": provenance.feature_visible_date,
                    "feature_generated_date": provenance.feature_generated_date,
                    "feature_vintage_date": provenance.feature_vintage_date,
                    "model_provenance": provenance.model_provenance,
                    "data_provenance": provenance.data_provenance,
                }
            )
    return (
        pd.DataFrame(records, columns=ASSET_FORECAST_DRAW_COLUMNS)
        .sort_values(
            ["asset_id", "draw_id", "horizon_months"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _constant(frame: pd.DataFrame, column: str) -> object:
    values = frame[column].drop_duplicates().tolist()
    if len(values) != 1:
        raise ValueError(f"{column} must be constant in governed channel outputs")
    return values[0]


def _summary(
    draws: pd.DataFrame,
    *,
    forecast_input: AssetForecastInput,
    config: AssetForecastConfig,
    posteriors: Mapping[str, _AssetPosterior],
    supports: Mapping[str, _AssetSupport],
    provenance_by_asset: Mapping[str, _AssetProvenance],
) -> pd.DataFrame:
    scenario = forecast_input.scenario_catalog.get(forecast_input.scenario_id)
    records = []
    for asset_id, posterior in posteriors.items():
        support = supports[asset_id]
        provenance = provenance_by_asset[asset_id]
        asset_draws = draws.loc[draws["asset_id"].eq(asset_id)]
        for horizon in config.horizons:
            horizon_draws = asset_draws.loc[asset_draws["horizon_months"].eq(horizon)]
            for return_basis in RETURN_BASES:
                if support.available:
                    return_column = (
                        "absolute_return"
                        if return_basis == "absolute"
                        else "excess_return"
                    )
                    drawdown_column = (
                        "absolute_max_drawdown"
                        if return_basis == "absolute"
                        else "excess_max_drawdown"
                    )
                    returns = horizon_draws[return_column].to_numpy(dtype="float64")
                    drawdowns = horizon_draws[drawdown_column].to_numpy(dtype="float64")
                    q10, q25, q50, q75, q90 = np.quantile(
                        returns,
                        [0.10, 0.25, 0.50, 0.75, 0.90],
                    )
                    risk = summarize_risk(returns, drawdowns)
                    metrics: dict[str, object] = {
                        "q10": float(q10),
                        "q25": float(q25),
                        "q50": float(q50),
                        "median": float(q50),
                        "q75": float(q75),
                        "q90": float(q90),
                        "interval50_lower": float(q25),
                        "interval50_upper": float(q75),
                        "interval80_lower": float(q10),
                        "interval80_upper": float(q90),
                        "expected_return": float(np.mean(returns)),
                        "volatility": risk.volatility,
                        "var95": risk.var95,
                        "cvar95": risk.cvar95,
                        "drawdown_q50": risk.drawdown_q50,
                        "drawdown_q80": risk.drawdown_q80,
                        "drawdown_q95": risk.drawdown_q95,
                    }
                    status = "available"
                    reason = None
                else:
                    metrics = {
                        key: np.nan
                        for key in (
                            "q10",
                            "q25",
                            "q50",
                            "median",
                            "q75",
                            "q90",
                            "interval50_lower",
                            "interval50_upper",
                            "interval80_lower",
                            "interval80_upper",
                            "expected_return",
                            "volatility",
                            "var95",
                            "cvar95",
                            "drawdown_q50",
                            "drawdown_q80",
                            "drawdown_q95",
                        )
                    }
                    status = "unavailable"
                    reason = support.reason
                records.append(
                    {
                        "asset_id": asset_id,
                        "scenario_id": scenario.scenario_id,
                        "horizon_months": horizon,
                        "return_basis": return_basis,
                        **metrics,
                        "effective_samples": support.effective_samples,
                        "stage2_effective_training_count": (
                            support.stage2_effective_training_count
                        ),
                        "channel_training_count": support.channel_training_count,
                        "status": status,
                        "unavailable_reason": reason,
                        "scenario_version": scenario.version,
                        "catalog_version": forecast_input.scenario_catalog.catalog_version,
                        "scenario_config_hash": forecast_input.scenario_catalog.config_hash,
                        "asset_forecast_model_version": config.model_version,
                        "asset_forecast_config_hash": _config_hash(config),
                        "channel_forecast_model_version": (
                            provenance.channel_forecast_model_version
                        ),
                        "channel_forecast_config_hash": (
                            provenance.channel_forecast_config_hash
                        ),
                        "channel_registry_hash": provenance.channel_registry_hash,
                        "cycle_forecast_model_version": (
                            provenance.cycle_forecast_model_version
                        ),
                        "cycle_forecast_config_hash": (
                            provenance.cycle_forecast_config_hash
                        ),
                        "cycle_registry_hash": provenance.cycle_registry_hash,
                        "stage2_posterior_date": posterior.posterior_date.date(),
                        "stage2_estimation_method": (
                            provenance.stage2_estimation_method
                        ),
                        "forecast_origin": forecast_input.as_of,
                        "data_vintage": provenance.data_vintage,
                        "feature_visible_date": provenance.feature_visible_date,
                        "feature_generated_date": provenance.feature_generated_date,
                        "feature_vintage_date": provenance.feature_vintage_date,
                        "model_provenance": provenance.model_provenance,
                        "data_provenance": provenance.data_provenance,
                    }
                )
    return (
        pd.DataFrame(records, columns=ASSET_FORECAST_SUMMARY_COLUMNS)
        .sort_values(
            ["asset_id", "horizon_months", "return_basis"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _generate_outputs(
    forecast_input: AssetForecastInput,
    config: AssetForecastConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    posteriors = _select_stage2(forecast_input)
    supports = _asset_supports(
        forecast_input,
        posteriors=posteriors,
        config=config,
    )
    provenance_by_asset = {
        asset_id: _asset_provenance(
            forecast_input,
            config=config,
            posterior=posterior,
        )
        for asset_id, posterior in posteriors.items()
    }
    channel_paths = _channel_paths(forecast_input, config=config)
    components, monthly = _components_and_monthly(
        forecast_input,
        config=config,
        posteriors=posteriors,
        supports=supports,
        provenance_by_asset=provenance_by_asset,
        channel_paths=channel_paths,
    )
    draws = _horizon_draws(
        monthly,
        forecast_input=forecast_input,
        config=config,
        provenance_by_asset=provenance_by_asset,
    )
    summary = _summary(
        draws,
        forecast_input=forecast_input,
        config=config,
        posteriors=posteriors,
        supports=supports,
        provenance_by_asset=provenance_by_asset,
    )
    return summary, monthly, draws, components, channel_paths


def _canonical_result_frame(values: object, *, name: str) -> pd.DataFrame:
    columns, sort_keys = _RESULT_SPECS[name]
    frame = _required_frame(values, name=name, columns=columns)
    if frame.duplicated(sort_keys).any():
        raise ValueError(f"{name} contains duplicate retained dimensions")
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty and np.isinf(numeric.to_numpy(dtype="float64")).any():
        raise ValueError(f"{name} numeric values cannot be infinite")
    return frame.sort_values(sort_keys, kind="stable").reset_index(drop=True)


@dataclass(frozen=True)
class AssetForecastResult:
    """Detached asset paths and aggregates rebuilt from retained governed inputs."""

    summary: pd.DataFrame
    monthly_draws: pd.DataFrame
    draws: pd.DataFrame
    components: pd.DataFrame
    channel_paths: pd.DataFrame
    forecast_input: AssetForecastInput
    config: AssetForecastConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, AssetForecastConfig):
            raise TypeError("config must be an AssetForecastConfig")
        forecast_input = _rebuild_asset_input(self.forecast_input)
        supplied = {
            name: _canonical_result_frame(
                object.__getattribute__(self, name),
                name=name,
            )
            for name in _RESULT_SPECS
        }
        generated = dict(
            zip(
                ("summary", "monthly_draws", "draws", "components", "channel_paths"),
                _generate_outputs(forecast_input, self.config),
                strict=True,
            )
        )
        for name, values in generated.items():
            expected = _canonical_result_frame(values, name=name)
            try:
                pd.testing.assert_frame_equal(
                    supplied[name],
                    expected,
                    check_dtype=True,
                    check_exact=True,
                )
            except AssertionError as error:
                raise ValueError(
                    f"{name} is inconsistent with retained deterministic replay"
                ) from error
            object.__setattr__(self, name, expected.copy(deep=True))
        object.__setattr__(self, "forecast_input", forecast_input)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    @property
    def retained_draws(self) -> pd.DataFrame:
        return self.draws

    @property
    def retained_monthly_draws(self) -> pd.DataFrame:
        return self.monthly_draws


def forecast_asset_distributions(
    forecast_input: AssetForecastInput,
    *,
    config: AssetForecastConfig | None = None,
) -> AssetForecastResult:
    """Generate auditable baseline or shocked joint 3/6/12-month distributions."""

    normalized_input = _rebuild_asset_input(forecast_input)
    normalized_config = config or AssetForecastConfig()
    if not isinstance(normalized_config, AssetForecastConfig):
        raise TypeError("config must be an AssetForecastConfig")
    summary, monthly, draws, components, channel_paths = _generate_outputs(
        normalized_input,
        normalized_config,
    )
    return AssetForecastResult(
        summary=summary,
        monthly_draws=monthly,
        draws=draws,
        components=components,
        channel_paths=channel_paths,
        forecast_input=normalized_input,
        config=normalized_config,
    )


forecast_future_assets = forecast_asset_distributions
generate_future_asset_distributions = forecast_asset_distributions


__all__ = [
    "ASSET_FORECAST_COMPONENT_COLUMNS",
    "ASSET_FORECAST_DRAW_COLUMNS",
    "ASSET_FORECAST_MONTHLY_COLUMNS",
    "ASSET_FORECAST_SUMMARY_COLUMNS",
    "BENCHMARK_FORECAST_INPUT_COLUMNS",
    "CONTROL_FORECAST_INPUT_COLUMNS",
    "EVENT_FORECAST_INPUT_COLUMNS",
    "HORIZONS",
    "INTERACTION_FORECAST_INPUT_COLUMNS",
    "POSITIONING_FORECAST_INPUT_COLUMNS",
    "RESIDUAL_FORECAST_INPUT_COLUMNS",
    "RETURN_BASES",
    "SCENARIO_CHANNEL_PATH_COLUMNS",
    "VALUATION_FORECAST_INPUT_COLUMNS",
    "AssetForecastConfig",
    "AssetForecastInput",
    "AssetForecastResult",
    "forecast_asset_distributions",
    "forecast_future_assets",
    "generate_future_asset_distributions",
]
