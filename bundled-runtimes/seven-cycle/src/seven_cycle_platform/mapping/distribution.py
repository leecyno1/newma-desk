"""Point-in-time current asset return and risk distributions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
import hashlib
from numbers import Integral, Real
from types import MappingProxyType
from typing import Protocol

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.stage1 import (
    CYCLE_IDS,
    CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS,
    CYCLE_TO_CHANNEL_PATH_COLUMNS,
    CycleToChannelResult,
)
from seven_cycle_platform.attribution.stage2 import (
    CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    ChannelToAssetResult,
)
from seven_cycle_platform.mapping.features import CurrentFeatureSnapshot
from seven_cycle_platform.mapping.risk import compute_max_drawdown, summarize_risk
from seven_cycle_platform.storage import RUN_ID_PATTERN


HORIZONS = (3, 6, 12)
RETURN_BASES = ("absolute", "excess")

CYCLE_FORECAST_COLUMNS = (
    "forecast_origin",
    "date",
    "draw_id",
    "cycle_id",
    "cycle_forecast",
)
CHANNEL_RESIDUAL_FORECAST_COLUMNS = (
    "forecast_origin",
    "date",
    "draw_id",
    "channel_id",
    "channel_residual",
)
PREDICTOR_FORECAST_COLUMNS = (
    "forecast_origin",
    "date",
    "draw_id",
    "asset_id",
    "component_type",
    "component_id",
    "predictor_value",
)
BENCHMARK_FORECAST_COLUMNS = (
    "forecast_origin",
    "date",
    "draw_id",
    "asset_id",
    "benchmark_return",
)
RESIDUAL_HISTORY_COLUMNS = ("date", "asset_id", "residual")

CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS = (
    "asset_id",
    "draw_id",
    "month_number",
    "date",
    "forecast_origin",
    "asset_monthly_return",
    "benchmark_monthly_return",
    "relative_monthly_return",
    "run_id",
    "snapshot_as_of",
)
CURRENT_DISTRIBUTION_DRAW_COLUMNS = (
    "asset_id",
    "draw_id",
    "horizon_months",
    "absolute_return",
    "benchmark_return",
    "excess_return",
    "absolute_max_drawdown",
    "excess_max_drawdown",
    "run_id",
    "snapshot_as_of",
)
CURRENT_DISTRIBUTION_SUMMARY_COLUMNS = (
    "asset_id",
    "horizon_months",
    "return_basis",
    "raw_up_probability",
    "raw_neutral_probability",
    "raw_down_probability",
    "up_probability",
    "neutral_probability",
    "down_probability",
    "q10",
    "q25",
    "q50",
    "q75",
    "q90",
    "expected_return",
    "volatility",
    "var95",
    "cvar95",
    "drawdown_q50",
    "drawdown_q80",
    "drawdown_q95",
    "effective_samples",
    "stage1_training_count",
    "stage2_effective_training_count",
    "residual_history_count",
    "status",
    "calibration_version",
    "run_id",
    "snapshot_as_of",
    "snapshot_data_vintage",
    "snapshot_model_version",
    "snapshot_config_hash",
    "stage1_posterior_date",
    "stage2_posterior_date",
    "forecast_origin",
)

_RESULT_FRAME_FIELDS = frozenset({"summary", "monthly_draws", "draws"})
_PREDICTOR_TYPES = frozenset({"interaction", "control", "event"})
_COMPONENT_ORDER = {
    "intercept": 0,
    "benchmark": 1,
    "channel": 2,
    "interaction": 3,
    "control": 4,
    "event": 5,
}
_USABLE_STAGE2_STATUSES = frozenset({"estimated", "parent_informed", "parent_only"})


def _default_neutral_bands() -> dict[tuple[str, int], float]:
    return {
        ("absolute", 3): 0.015,
        ("absolute", 6): 0.025,
        ("absolute", 12): 0.040,
        ("excess", 3): 0.010,
        ("excess", 6): 0.018,
        ("excess", 12): 0.030,
    }


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


def _finite_nonnegative(value: object, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a finite real number")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    if numeric < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return numeric


def _nonnegative_real_floor(value: object, *, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must be a nonnegative finite real number")
    numeric = float(value)
    if not np.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be a nonnegative finite real number")
    return int(np.floor(numeric))


@dataclass(frozen=True)
class CurrentDistributionConfig:
    """Immutable Monte Carlo, support, bootstrap, and direction configuration."""

    draw_count: int = 2_000
    seed: int = 0
    residual_block_length: int = 3
    min_effective_samples: int = 24
    neutral_bands: Mapping[tuple[str, int], float] = field(
        default_factory=_default_neutral_bands
    )

    def __post_init__(self) -> None:
        draw_count = _positive_integer(self.draw_count, name="draw_count")
        seed = _nonnegative_integer(self.seed, name="seed")
        block_length = _positive_integer(
            self.residual_block_length,
            name="residual_block_length",
        )
        minimum = _positive_integer(
            self.min_effective_samples,
            name="min_effective_samples",
        )
        if not isinstance(self.neutral_bands, Mapping):
            raise TypeError("neutral_bands must be a mapping")
        expected = {
            (return_basis, horizon)
            for return_basis in RETURN_BASES
            for horizon in HORIZONS
        }
        supplied = set(self.neutral_bands)
        if supplied != expected:
            raise ValueError(
                "neutral_bands must explicitly define absolute/excess for 3/6/12"
            )
        bands = {
            key: _finite_nonnegative(
                self.neutral_bands[key],
                name=f"neutral band {key}",
            )
            for key in sorted(expected)
        }
        object.__setattr__(self, "draw_count", draw_count)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "residual_block_length", block_length)
        object.__setattr__(self, "min_effective_samples", minimum)
        object.__setattr__(self, "neutral_bands", MappingProxyType(bands))


class ProbabilityCalibrator(Protocol):
    """Probability-only calibration hook."""

    version: str

    def calibrate(
        self,
        *,
        probabilities: dict[str, float],
        asset_id: str,
        horizon_months: int,
        return_basis: str,
    ) -> Mapping[str, float]: ...


@dataclass(frozen=True)
class IdentityProbabilityCalibrator:
    """Identity calibration with explicit audit version."""

    version: str = "identity-v1"

    def calibrate(
        self,
        *,
        probabilities: dict[str, float],
        asset_id: str,
        horizon_months: int,
        return_basis: str,
    ) -> Mapping[str, float]:
        del asset_id, horizon_months, return_basis
        return dict(probabilities)


@dataclass(frozen=True)
class _Stage1Posterior:
    channel_id: str
    mean: np.ndarray
    covariance: np.ndarray
    intercept: float
    training_count: int
    usable: bool


@dataclass(frozen=True)
class _Stage2Posterior:
    asset_id: str
    labels: tuple[tuple[str, str], ...]
    mean: np.ndarray
    covariance: np.ndarray
    effective_training_count: int
    usable: bool


@dataclass(frozen=True)
class _AssetSupport:
    effective_samples: int
    stage1_training_count: int
    stage2_effective_training_count: int
    residual_history_count: int
    available: bool


def direction_probabilities(
    returns: object,
    *,
    neutral_band: float,
) -> dict[str, float]:
    """Classify returns with inclusive neutral boundaries."""

    values = np.asarray(returns, dtype="float64")
    if values.ndim != 1 or values.size == 0:
        raise ValueError("returns must be a non-empty one-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("returns must contain only finite values")
    band = _finite_nonnegative(neutral_band, name="neutral_band")
    return {
        "up": float(np.mean(values > band)),
        "neutral": float(np.mean((values >= -band) & (values <= band))),
        "down": float(np.mean(values < -band)),
    }


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


def _require_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if tuple(values.columns) != columns:
        raise ValueError(f"{name} columns do not match the contract")
    return values.copy(deep=True)


def _frame_attribute(
    values: object,
    *,
    attribute: str,
    name: str,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    try:
        frame = getattr(values, attribute)
    except AttributeError as error:
        raise TypeError(f"{name} must expose {attribute}") from error
    return _require_frame(frame, name=f"{name}.{attribute}", columns=columns)


def _normalize_dates(values: pd.Series, *, name: str) -> pd.Series:
    normalized: list[pd.Timestamp] = []
    for value in values.tolist():
        if pd.isna(value):
            raise ValueError(f"{name} cannot contain missing dates")
        if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
            raise TypeError(f"{name} must contain date-like values")
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{name} must contain valid dates") from error
        if timestamp.tzinfo is not None:
            raise ValueError(f"{name} dates must be timezone-naive")
        normalized.append(timestamp.normalize())
    return pd.Series(normalized, index=values.index, dtype="datetime64[ns]")


def _normalize_identifiers(values: pd.Series, *, name: str) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must contain non-empty strings")
        normalized.append(value.strip())
    return pd.Series(normalized, index=values.index, dtype="object")


def _normalize_draw_ids(values: pd.Series, *, name: str) -> pd.Series:
    normalized = [_nonnegative_integer(value, name=name) for value in values.tolist()]
    return pd.Series(normalized, index=values.index, dtype="int64")


def _normalize_numeric(values: pd.Series, *, name: str) -> pd.Series:
    normalized: list[float] = []
    for value in values.tolist():
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (Real, np.integer, np.floating),
        ):
            raise TypeError(f"{name} must contain real numbers")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"{name} must contain finite values")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _future_dates(as_of: date) -> pd.DatetimeIndex:
    first = pd.Timestamp(as_of) + pd.offsets.MonthEnd(1)
    return pd.date_range(first, periods=12, freq="ME")


def _matrix_sqrt(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("covariance must be square")
    if not np.isfinite(matrix).all():
        raise ValueError("covariance must contain finite values")
    if not np.allclose(matrix, matrix.T, atol=1e-10, rtol=1e-10):
        raise ValueError("covariance must be symmetric")
    symmetric = (matrix + matrix.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    if float(eigenvalues.min()) < -1e-10 * scale:
        raise ValueError("covariance must be positive semidefinite")
    return eigenvectors @ np.diag(np.sqrt(np.clip(eigenvalues, 0.0, None)))


def _long_covariance(
    frame: pd.DataFrame,
    labels: tuple[object, ...],
    *,
    row_columns: tuple[str, ...],
    column_columns: tuple[str, ...],
) -> np.ndarray:
    lookup: dict[tuple[object, object], float] = {}
    label_set = set(labels)
    for row in frame.itertuples(index=False):
        row_label: object
        column_label: object
        if len(row_columns) == 1:
            row_label = getattr(row, row_columns[0])
            column_label = getattr(row, column_columns[0])
        else:
            row_label = tuple(getattr(row, column) for column in row_columns)
            column_label = tuple(getattr(row, column) for column in column_columns)
        if row_label in label_set and column_label in label_set:
            lookup[(row_label, column_label)] = float(
                getattr(row, "coefficient_covariance")
            )
    expected = {(left, right) for left in labels for right in labels}
    if set(lookup) != expected:
        raise ValueError("covariance component pairs do not align with posterior")
    matrix = np.asarray(
        [[lookup[(left, right)] for right in labels] for left in labels],
        dtype="float64",
    )
    _matrix_sqrt(matrix)
    return matrix


def _select_stage1(
    stage1: object,
    *,
    snapshot: CurrentFeatureSnapshot,
) -> tuple[dict[str, _Stage1Posterior], pd.Timestamp]:
    paths = _frame_attribute(
        stage1,
        attribute="paths",
        name="stage1",
        columns=CYCLE_TO_CHANNEL_PATH_COLUMNS,
    )
    covariance = _frame_attribute(
        stage1,
        attribute="covariance",
        name="stage1",
        columns=CYCLE_TO_CHANNEL_COVARIANCE_COLUMNS,
    )
    paths["date"] = _normalize_dates(paths["date"], name="stage1 path date")
    covariance["date"] = _normalize_dates(
        covariance["date"],
        name="stage1 covariance date",
    )
    cutoff = pd.Timestamp(snapshot.as_of)
    visible = paths.loc[paths["date"].le(cutoff)].copy()
    if visible.empty:
        raise ValueError("stage1 has no posterior visible at snapshot.as_of")
    latest = visible.groupby("channel_id", sort=True)["date"].max()
    if latest.nunique() != 1:
        raise ValueError("stage1 posterior dates cannot be mixed across channels")
    posterior_date = pd.Timestamp(latest.iloc[0])
    selected = visible.loc[visible["date"].eq(posterior_date)].copy()
    selected_covariance = covariance.loc[covariance["date"].eq(posterior_date)].copy()
    snapshot_channels = {feature.feature_id for feature in snapshot.channel_states}
    selected_channels = set(selected["channel_id"])
    if selected_channels != snapshot_channels:
        raise ValueError("stage1 channels must align with snapshot channel features")

    posteriors: dict[str, _Stage1Posterior] = {}
    for channel_id in sorted(selected_channels):
        group = selected.loc[selected["channel_id"].eq(channel_id)].copy()
        if set(group["cycle_id"]) != set(CYCLE_IDS) or len(group) != len(CYCLE_IDS):
            raise ValueError("stage1 posterior must contain C1-C7 exactly once")
        group = group.set_index("cycle_id").loc[list(CYCLE_IDS)].reset_index()
        statuses = set(group["status"])
        if len(statuses) != 1:
            raise ValueError("stage1 status cannot vary within a channel")
        status = str(group["status"].iloc[0])
        means = _normalize_numeric(
            group["coefficient_mean"],
            name="stage1 coefficient_mean",
        ).to_numpy()
        intercepts = _normalize_numeric(
            group["intercept"],
            name="stage1 intercept",
        )
        if intercepts.nunique() != 1:
            raise ValueError("stage1 intercept must be constant within a channel")
        training_counts = [
            _nonnegative_integer(value, name="stage1 training_count")
            for value in group["training_count"].tolist()
        ]
        covariance_group = selected_covariance.loc[
            selected_covariance["channel_id"].eq(channel_id)
        ]
        matrix = _long_covariance(
            covariance_group,
            tuple(CYCLE_IDS),
            row_columns=("cycle_i",),
            column_columns=("cycle_j",),
        )
        posteriors[channel_id] = _Stage1Posterior(
            channel_id=channel_id,
            mean=means,
            covariance=matrix,
            intercept=float(intercepts.iloc[0]),
            training_count=min(training_counts),
            usable=status == "estimated",
        )
    return posteriors, posterior_date


def _select_stage2(
    stage2: object,
    *,
    snapshot: CurrentFeatureSnapshot,
) -> tuple[dict[str, _Stage2Posterior], pd.Timestamp]:
    components = _frame_attribute(
        stage2,
        attribute="components",
        name="stage2",
        columns=CHANNEL_TO_ASSET_COMPONENT_COLUMNS,
    )
    posteriors = _frame_attribute(
        stage2,
        attribute="posteriors",
        name="stage2",
        columns=CHANNEL_TO_ASSET_POSTERIOR_COLUMNS,
    )
    covariance = _frame_attribute(
        stage2,
        attribute="covariance",
        name="stage2",
        columns=CHANNEL_TO_ASSET_COVARIANCE_COLUMNS,
    )
    for frame, name in (
        (components, "stage2 component date"),
        (posteriors, "stage2 posterior date"),
        (covariance, "stage2 covariance date"),
    ):
        frame["date"] = _normalize_dates(frame["date"], name=name)
    cutoff = pd.Timestamp(snapshot.as_of)
    asset_rows = posteriors.loc[
        posteriors["node_level"].eq("asset") & posteriors["date"].le(cutoff)
    ].copy()
    if asset_rows.empty:
        raise ValueError("stage2 has no asset posterior visible at snapshot.as_of")
    latest = asset_rows.groupby("node_id", sort=True)["date"].max()
    if latest.nunique() != 1:
        raise ValueError("stage2 posterior dates cannot be mixed across assets")
    posterior_date = pd.Timestamp(latest.iloc[0])
    selected = asset_rows.loc[asset_rows["date"].eq(posterior_date)].copy()
    selected_covariance = covariance.loc[
        covariance["node_level"].eq("asset") & covariance["date"].eq(posterior_date)
    ].copy()
    selected_components = components.loc[components["date"].eq(posterior_date)].copy()
    snapshot_assets = {
        feature.entity_id
        for feature in snapshot.historical_posterior
        if feature.entity_id is not None
    }
    selected_assets = set(selected["node_id"])
    if selected_assets != snapshot_assets:
        raise ValueError(
            "stage2 assets must exactly align with snapshot historical posterior assets"
        )

    normalized: dict[str, _Stage2Posterior] = {}
    for asset_id in sorted(selected_assets):
        group = selected.loc[selected["node_id"].eq(asset_id)].copy()
        component_group = selected_components.loc[
            selected_components["asset_id"].eq(asset_id)
        ]
        if component_group.empty:
            raise ValueError("stage2 components must align with asset posterior date")
        statuses = set(group["status"])
        if len(statuses) != 1:
            raise ValueError("stage2 status cannot vary within an asset posterior")
        status = str(group["status"].iloc[0])
        labels = tuple(
            sorted(
                zip(
                    group["component_type"],
                    group["component_id"],
                    strict=True,
                ),
                key=lambda item: (_COMPONENT_ORDER.get(item[0], 99), item[1]),
            )
        )
        if len(labels) != len(set(labels)):
            raise ValueError("stage2 posterior components must be unique")
        if any(component_type not in _COMPONENT_ORDER for component_type, _ in labels):
            raise ValueError("stage2 posterior contains an unsupported component type")
        if sum(label[0] == "intercept" for label in labels) != 1:
            raise ValueError("stage2 posterior requires exactly one intercept")
        if not any(label[0] == "channel" for label in labels):
            raise ValueError("stage2 posterior requires at least one channel")
        indexed = group.set_index(["component_type", "component_id"])
        means = _normalize_numeric(
            pd.Series([indexed.loc[label, "coefficient_mean"] for label in labels]),
            name="stage2 coefficient_mean",
        ).to_numpy()
        effective_counts = [
            _nonnegative_real_floor(
                value,
                name="stage2 effective_training_count",
            )
            for value in group["effective_training_count"].tolist()
        ]
        covariance_group = selected_covariance.loc[
            selected_covariance["node_id"].eq(asset_id)
        ]
        matrix = _long_covariance(
            covariance_group,
            labels,
            row_columns=("component_i_type", "component_i_id"),
            column_columns=("component_j_type", "component_j_id"),
        )
        normalized[asset_id] = _Stage2Posterior(
            asset_id=asset_id,
            labels=labels,
            mean=means,
            covariance=matrix,
            effective_training_count=min(effective_counts),
            usable=status in _USABLE_STAGE2_STATUSES,
        )
    return normalized, posterior_date


def _normalize_forecast_frame(
    values: object,
    *,
    name: str,
    columns: tuple[str, ...],
    identifier_columns: tuple[str, ...],
    value_column: str,
) -> pd.DataFrame:
    frame = _require_frame(values, name=name, columns=columns)
    frame["forecast_origin"] = _normalize_dates(
        frame["forecast_origin"],
        name=f"{name} forecast_origin",
    )
    frame["date"] = _normalize_dates(frame["date"], name=f"{name} date")
    frame["draw_id"] = _normalize_draw_ids(
        frame["draw_id"],
        name=f"{name} draw_id",
    )
    for column in identifier_columns:
        frame[column] = _normalize_identifiers(
            frame[column],
            name=f"{name} {column}",
        )
    frame[value_column] = _normalize_numeric(
        frame[value_column],
        name=f"{name} {value_column}",
    )
    return frame


def _validate_forecast_surface(
    frame: pd.DataFrame,
    *,
    name: str,
    snapshot: CurrentFeatureSnapshot,
    config: CurrentDistributionConfig,
    expected_dates: pd.DatetimeIndex,
) -> None:
    if set(frame["forecast_origin"]) != {pd.Timestamp(snapshot.as_of)}:
        raise ValueError(f"{name} forecast_origin must equal snapshot.as_of")
    if set(frame["date"]) != set(expected_dates):
        raise ValueError(f"{name} must cover continuous 12-month future dates")
    if set(frame["draw_id"]) != set(range(config.draw_count)):
        raise ValueError(f"{name} draw_id must be exactly 0 through draw_count - 1")


def _normalize_forecasts(
    *,
    snapshot: CurrentFeatureSnapshot,
    config: CurrentDistributionConfig,
    channels: tuple[str, ...],
    assets: tuple[str, ...],
    stage2: Mapping[str, _Stage2Posterior],
    cycle_forecasts: object,
    channel_residual_forecasts: object,
    predictor_forecasts: object | None,
    benchmark_forecasts: object,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expected_dates = _future_dates(snapshot.as_of)
    cycles = _normalize_forecast_frame(
        cycle_forecasts,
        name="cycle_forecasts",
        columns=CYCLE_FORECAST_COLUMNS,
        identifier_columns=("cycle_id",),
        value_column="cycle_forecast",
    )
    _validate_forecast_surface(
        cycles,
        name="cycle_forecasts",
        snapshot=snapshot,
        config=config,
        expected_dates=expected_dates,
    )
    if set(cycles["cycle_id"]) != set(CYCLE_IDS):
        raise ValueError("cycle_forecasts must contain exactly C1-C7")
    if cycles.duplicated(["date", "draw_id", "cycle_id"]).any() or len(cycles) != (
        config.draw_count * 12 * len(CYCLE_IDS)
    ):
        raise ValueError("cycle_forecasts must contain a complete unique draw surface")

    channel_residuals = _normalize_forecast_frame(
        channel_residual_forecasts,
        name="channel_residual_forecasts",
        columns=CHANNEL_RESIDUAL_FORECAST_COLUMNS,
        identifier_columns=("channel_id",),
        value_column="channel_residual",
    )
    _validate_forecast_surface(
        channel_residuals,
        name="channel_residual_forecasts",
        snapshot=snapshot,
        config=config,
        expected_dates=expected_dates,
    )
    if set(channel_residuals["channel_id"]) != set(channels):
        raise ValueError("channel residual forecasts must align with stage1 channels")
    if channel_residuals.duplicated(["date", "draw_id", "channel_id"]).any() or len(
        channel_residuals
    ) != config.draw_count * 12 * len(channels):
        raise ValueError(
            "channel residual forecasts must contain a complete unique draw surface"
        )

    benchmarks = _normalize_forecast_frame(
        benchmark_forecasts,
        name="benchmark_forecasts",
        columns=BENCHMARK_FORECAST_COLUMNS,
        identifier_columns=("asset_id",),
        value_column="benchmark_return",
    )
    _validate_forecast_surface(
        benchmarks,
        name="benchmark_forecasts",
        snapshot=snapshot,
        config=config,
        expected_dates=expected_dates,
    )
    if set(benchmarks["asset_id"]) != set(assets):
        raise ValueError("benchmark forecasts must align with stage2 assets")
    if benchmarks.duplicated(["date", "draw_id", "asset_id"]).any() or len(
        benchmarks
    ) != config.draw_count * 12 * len(assets):
        raise ValueError(
            "benchmark forecasts must contain a complete unique draw surface"
        )
    if bool((benchmarks["benchmark_return"] <= -1.0).any()):
        raise ValueError("benchmark monthly returns must be greater than -1 (-100%)")

    if predictor_forecasts is None:
        predictors = pd.DataFrame(columns=PREDICTOR_FORECAST_COLUMNS)
    else:
        predictors = _normalize_forecast_frame(
            predictor_forecasts,
            name="predictor_forecasts",
            columns=PREDICTOR_FORECAST_COLUMNS,
            identifier_columns=("asset_id", "component_type", "component_id"),
            value_column="predictor_value",
        )
    required_predictors = {
        (asset_id, component_type, component_id)
        for asset_id, posterior in stage2.items()
        for component_type, component_id in posterior.labels
        if component_type in _PREDICTOR_TYPES
    }
    supplied_predictors = set(
        zip(
            predictors["asset_id"],
            predictors["component_type"],
            predictors["component_id"],
            strict=True,
        )
    )
    if supplied_predictors != required_predictors:
        missing = sorted(required_predictors - supplied_predictors)
        details = ", ".join("/".join(value) for value in missing)
        raise ValueError(f"missing required predictor forecast: {details}")
    if required_predictors:
        _validate_forecast_surface(
            predictors,
            name="predictor_forecasts",
            snapshot=snapshot,
            config=config,
            expected_dates=expected_dates,
        )
        if predictors.duplicated(
            ["date", "draw_id", "asset_id", "component_type", "component_id"]
        ).any() or len(predictors) != (
            config.draw_count * 12 * len(required_predictors)
        ):
            raise ValueError(
                "predictor forecasts must contain a complete unique draw surface"
            )
    return (
        cycles.sort_values(["draw_id", "date", "cycle_id"], kind="stable").reset_index(
            drop=True
        ),
        channel_residuals.sort_values(
            ["draw_id", "date", "channel_id"], kind="stable"
        ).reset_index(drop=True),
        predictors.sort_values(
            ["draw_id", "date", "asset_id", "component_type", "component_id"],
            kind="stable",
        ).reset_index(drop=True),
        benchmarks.sort_values(
            ["draw_id", "date", "asset_id"], kind="stable"
        ).reset_index(drop=True),
    )


def _normalize_residual_history(
    values: object,
    *,
    snapshot: CurrentFeatureSnapshot,
    assets: tuple[str, ...],
) -> dict[str, np.ndarray]:
    frame = _require_frame(
        values,
        name="residual_history",
        columns=RESIDUAL_HISTORY_COLUMNS,
    )
    frame["date"] = _normalize_dates(frame["date"], name="residual history date")
    frame["asset_id"] = _normalize_identifiers(
        frame["asset_id"],
        name="residual history asset_id",
    )
    frame["residual"] = _normalize_numeric(
        frame["residual"],
        name="residual history residual",
    )
    frame = frame.loc[frame["date"].lt(pd.Timestamp(snapshot.as_of))].copy()
    normalized: dict[str, np.ndarray] = {}
    for asset_id in assets:
        group = frame.loc[frame["asset_id"].eq(asset_id)].sort_values(
            "date", kind="stable"
        )
        if group.duplicated("date").any():
            raise ValueError("residual history dates must be unique per asset")
        if not group.empty:
            dates = pd.DatetimeIndex(group["date"])
            expected = pd.date_range(dates.min(), dates.max(), freq="ME")
            if not dates.equals(expected):
                raise ValueError(
                    "residual history must be consecutive and cannot bridge a gap"
                )
        normalized[asset_id] = group["residual"].to_numpy(dtype="float64", copy=True)
    return normalized


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
    square_root = _matrix_sqrt(covariance)
    standard = generator.standard_normal((draw_count, len(mean)))
    return mean + standard @ square_root.T


def _bootstrap_paths(
    history: np.ndarray,
    *,
    config: CurrentDistributionConfig,
    generator: np.random.Generator,
) -> np.ndarray:
    centered = history - float(np.mean(history))
    maximum_start = len(centered) - config.residual_block_length
    paths = np.zeros((config.draw_count, 12), dtype="float64")
    for draw_position in range(config.draw_count):
        sampled: list[float] = []
        while len(sampled) < 12:
            start = int(generator.integers(0, maximum_start + 1))
            sampled.extend(
                centered[start : start + config.residual_block_length]
                .astype("float64")
                .tolist()
            )
        paths[draw_position] = sampled[:12]
    return paths


def _cube(
    frame: pd.DataFrame,
    *,
    labels: tuple[str, ...],
    label_column: str,
    value_column: str,
    draw_count: int,
    dates: pd.DatetimeIndex,
) -> np.ndarray:
    index = pd.MultiIndex.from_product(
        [range(draw_count), dates, labels],
        names=["draw_id", "date", label_column],
    )
    values = frame.set_index(["draw_id", "date", label_column])[value_column].reindex(
        index
    )
    if values.isna().any():
        raise ValueError(f"{value_column} forecast surface is incomplete")
    return values.to_numpy(dtype="float64").reshape(draw_count, 12, len(labels))


def _asset_matrix(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    value_column: str,
    draw_count: int,
    dates: pd.DatetimeIndex,
) -> np.ndarray:
    group = frame.loc[frame["asset_id"].eq(asset_id)]
    index = pd.MultiIndex.from_product(
        [range(draw_count), dates],
        names=["draw_id", "date"],
    )
    values = group.set_index(["draw_id", "date"])[value_column].reindex(index)
    if values.isna().any():
        raise ValueError(f"{value_column} forecast surface is incomplete")
    return values.to_numpy(dtype="float64").reshape(draw_count, 12)


def _predictor_matrix(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    component_type: str,
    component_id: str,
    draw_count: int,
    dates: pd.DatetimeIndex,
) -> np.ndarray:
    group = frame.loc[
        frame["asset_id"].eq(asset_id)
        & frame["component_type"].eq(component_type)
        & frame["component_id"].eq(component_id)
    ]
    index = pd.MultiIndex.from_product(
        [range(draw_count), dates],
        names=["draw_id", "date"],
    )
    values = group.set_index(["draw_id", "date"])["predictor_value"].reindex(index)
    if values.isna().any():
        raise ValueError(
            f"predictor forecast is incomplete for {asset_id}/{component_type}/{component_id}"
        )
    return values.to_numpy(dtype="float64").reshape(draw_count, 12)


def _calibrator_version(calibrator: object) -> str:
    version = getattr(calibrator, "version", None)
    if not isinstance(version, str) or not version.strip():
        raise ValueError("probability calibrator requires a non-empty version")
    if not callable(getattr(calibrator, "calibrate", None)):
        raise TypeError("probability calibrator requires a calibrate method")
    return version.strip()


def _calibrate(
    calibrator: ProbabilityCalibrator,
    *,
    probabilities: dict[str, float],
    asset_id: str,
    horizon_months: int,
    return_basis: str,
) -> dict[str, float]:
    calibrated = calibrator.calibrate(
        probabilities=dict(probabilities),
        asset_id=asset_id,
        horizon_months=horizon_months,
        return_basis=return_basis,
    )
    if not isinstance(calibrated, Mapping) or set(calibrated) != {
        "up",
        "neutral",
        "down",
    }:
        raise ValueError("calibrated probabilities must contain up/neutral/down")
    normalized = {key: float(calibrated[key]) for key in ("up", "neutral", "down")}
    if not np.isfinite(list(normalized.values())).all() or any(
        value < 0.0 or value > 1.0 for value in normalized.values()
    ):
        raise ValueError("calibrated probabilities must each be in [0, 1]")
    if not np.isclose(sum(normalized.values()), 1.0, atol=1e-10, rtol=1e-10):
        raise ValueError("calibrated probabilities must sum to one")
    return normalized


def _summary_records(
    *,
    assets: tuple[str, ...],
    draws: pd.DataFrame,
    supports: Mapping[str, _AssetSupport],
    config: CurrentDistributionConfig,
    calibrator: ProbabilityCalibrator,
    calibration_version: str,
    snapshot: CurrentFeatureSnapshot,
    stage1_date: pd.Timestamp,
    stage2_date: pd.Timestamp,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for asset_id in assets:
        support = supports[asset_id]
        asset_draws = draws.loc[draws["asset_id"].eq(asset_id)]
        for horizon in HORIZONS:
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
                    raw = direction_probabilities(
                        returns,
                        neutral_band=config.neutral_bands[(return_basis, horizon)],
                    )
                    probabilities = _calibrate(
                        calibrator,
                        probabilities=raw,
                        asset_id=asset_id,
                        horizon_months=horizon,
                        return_basis=return_basis,
                    )
                    q10, q25, q50, q75, q90 = np.quantile(
                        returns,
                        [0.10, 0.25, 0.50, 0.75, 0.90],
                    )
                    risk = summarize_risk(returns, drawdowns)
                    metrics: dict[str, object] = {
                        "raw_up_probability": raw["up"],
                        "raw_neutral_probability": raw["neutral"],
                        "raw_down_probability": raw["down"],
                        "up_probability": probabilities["up"],
                        "neutral_probability": probabilities["neutral"],
                        "down_probability": probabilities["down"],
                        "q10": float(q10),
                        "q25": float(q25),
                        "q50": float(q50),
                        "q75": float(q75),
                        "q90": float(q90),
                        "expected_return": float(np.mean(returns)),
                        "volatility": risk.volatility,
                        "var95": risk.var95,
                        "cvar95": risk.cvar95,
                        "drawdown_q50": risk.drawdown_q50,
                        "drawdown_q80": risk.drawdown_q80,
                        "drawdown_q95": risk.drawdown_q95,
                    }
                    status = "available"
                else:
                    metrics = {
                        column: np.nan
                        for column in CURRENT_DISTRIBUTION_SUMMARY_COLUMNS
                        if column
                        in {
                            "raw_up_probability",
                            "raw_neutral_probability",
                            "raw_down_probability",
                            "up_probability",
                            "neutral_probability",
                            "down_probability",
                            "q10",
                            "q25",
                            "q50",
                            "q75",
                            "q90",
                            "expected_return",
                            "volatility",
                            "var95",
                            "cvar95",
                            "drawdown_q50",
                            "drawdown_q80",
                            "drawdown_q95",
                        }
                    }
                    status = "unavailable"
                records.append(
                    {
                        "asset_id": asset_id,
                        "horizon_months": horizon,
                        "return_basis": return_basis,
                        **metrics,
                        "effective_samples": support.effective_samples,
                        "stage1_training_count": support.stage1_training_count,
                        "stage2_effective_training_count": (
                            support.stage2_effective_training_count
                        ),
                        "residual_history_count": support.residual_history_count,
                        "status": status,
                        "calibration_version": calibration_version,
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                        "snapshot_data_vintage": snapshot.provenance.data_vintage,
                        "snapshot_model_version": snapshot.provenance.model_version,
                        "snapshot_config_hash": snapshot.provenance.config_hash,
                        "stage1_posterior_date": stage1_date.date(),
                        "stage2_posterior_date": stage2_date.date(),
                        "forecast_origin": snapshot.as_of,
                    }
                )
    return records


def _close(left: object, right: float, *, name: str) -> None:
    if not np.isclose(float(left), right, atol=1e-10, rtol=1e-10):
        raise ValueError(f"{name} is inconsistent with retained draws")


def _constant_text(frame: pd.DataFrame, column: str, *, name: str) -> str | None:
    if frame.empty:
        return None
    values = frame[column].tolist()
    if any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in values
    ):
        raise ValueError(f"{name} provenance must contain non-empty text")
    if len(set(values)) != 1:
        raise ValueError(f"{name} provenance must be constant")
    return values[0]


def _constant_date(
    frame: pd.DataFrame,
    column: str,
    *,
    name: str,
) -> pd.Timestamp | None:
    if frame.empty:
        return None
    normalized = _normalize_dates(frame[column], name=f"{name} provenance")
    if normalized.nunique() != 1:
        raise ValueError(f"{name} provenance must be constant")
    return pd.Timestamp(normalized.iloc[0])


def _validate_result_provenance(
    summary: pd.DataFrame,
    monthly_draws: pd.DataFrame,
    draws: pd.DataFrame,
) -> None:
    if summary.empty:
        raise ValueError("summary must contain at least one asset")

    summary_run_id = _constant_text(summary, "run_id", name="summary run_id")
    summary_as_of = _constant_date(
        summary,
        "snapshot_as_of",
        name="summary snapshot_as_of",
    )
    data_vintage = _constant_date(
        summary,
        "snapshot_data_vintage",
        name="summary snapshot_data_vintage",
    )
    model_version = _constant_text(
        summary,
        "snapshot_model_version",
        name="summary snapshot_model_version",
    )
    config_hash = _constant_text(
        summary,
        "snapshot_config_hash",
        name="summary snapshot_config_hash",
    )
    stage1_date = _constant_date(
        summary,
        "stage1_posterior_date",
        name="summary stage1_posterior_date",
    )
    stage2_date = _constant_date(
        summary,
        "stage2_posterior_date",
        name="summary stage2_posterior_date",
    )
    summary_origin = _constant_date(
        summary,
        "forecast_origin",
        name="summary forecast_origin",
    )
    if summary_run_id is None or RUN_ID_PATTERN.fullmatch(summary_run_id) is None:
        raise ValueError("summary run_id provenance is invalid")
    if model_version is None:
        raise ValueError("summary snapshot_model_version provenance is invalid")
    if (
        config_hash is None
        or len(config_hash) != 64
        or any(character not in "0123456789abcdef" for character in config_hash)
    ):
        raise ValueError("summary snapshot_config_hash provenance is invalid")
    if (
        summary_as_of is None
        or data_vintage is None
        or stage1_date is None
        or stage2_date is None
        or summary_origin is None
    ):
        raise ValueError("summary date provenance is incomplete")
    if data_vintage > summary_as_of:
        raise ValueError("snapshot_data_vintage cannot follow snapshot_as_of")
    if stage1_date > summary_as_of or stage2_date > summary_as_of:
        raise ValueError("posterior date provenance cannot follow snapshot_as_of")
    if summary_origin != summary_as_of:
        raise ValueError("summary forecast_origin must equal snapshot_as_of")

    monthly_run_id = _constant_text(
        monthly_draws,
        "run_id",
        name="monthly_draws run_id",
    )
    monthly_as_of = _constant_date(
        monthly_draws,
        "snapshot_as_of",
        name="monthly_draws snapshot_as_of",
    )
    monthly_origin = _constant_date(
        monthly_draws,
        "forecast_origin",
        name="monthly_draws forecast_origin",
    )
    draw_run_id = _constant_text(draws, "run_id", name="draws run_id")
    draw_as_of = _constant_date(
        draws,
        "snapshot_as_of",
        name="draws snapshot_as_of",
    )
    if monthly_run_id is not None and monthly_run_id != summary_run_id:
        raise ValueError("monthly_draws run_id provenance must match summary")
    if draw_run_id is not None and draw_run_id != summary_run_id:
        raise ValueError("draws run_id provenance must match summary")
    if monthly_as_of is not None and monthly_as_of != summary_as_of:
        raise ValueError("monthly_draws snapshot_as_of provenance must match summary")
    if draw_as_of is not None and draw_as_of != summary_as_of:
        raise ValueError("draws snapshot_as_of provenance must match summary")
    if monthly_origin is not None and monthly_origin != summary_origin:
        raise ValueError("monthly_draws forecast_origin provenance must match summary")
    if monthly_origin is not None and monthly_origin != monthly_as_of:
        raise ValueError("monthly_draws forecast_origin must equal snapshot_as_of")


def _validate_asset_coverage(
    summary: pd.DataFrame,
    monthly_draws: pd.DataFrame,
    draws: pd.DataFrame,
    config: CurrentDistributionConfig,
) -> None:
    if not set(summary["status"]).issubset({"available", "unavailable"}):
        raise ValueError("summary contains an unknown status")
    if bool(summary.groupby("asset_id", sort=False)["status"].nunique().gt(1).any()):
        raise ValueError("summary status must be constant within each asset")

    support_columns = (
        "effective_samples",
        "stage1_training_count",
        "stage2_effective_training_count",
        "residual_history_count",
    )
    for asset_id, asset_summary in summary.groupby("asset_id", sort=False):
        support: dict[str, int] = {}
        for column in support_columns:
            try:
                normalized = [
                    _nonnegative_integer(value, name=column)
                    for value in asset_summary[column].tolist()
                ]
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{column} support must contain nonnegative integers"
                ) from error
            if len(set(normalized)) != 1:
                raise ValueError(
                    f"{column} support must be constant within asset {asset_id}"
                )
            support[column] = normalized[0]
        expected_effective = min(
            support["stage1_training_count"],
            support["stage2_effective_training_count"],
            support["residual_history_count"],
        )
        if support["effective_samples"] != expected_effective:
            raise ValueError(
                "effective_samples must equal the conservative support minimum"
            )
        if str(asset_summary["status"].iloc[0]) == "available":
            if support["effective_samples"] < config.min_effective_samples:
                raise ValueError(
                    "available asset support is below min_effective_samples"
                )
            if support["residual_history_count"] < config.residual_block_length:
                raise ValueError(
                    "available asset residual support is below block length"
                )

    available_assets = set(summary.loc[summary["status"].eq("available"), "asset_id"])
    monthly_assets = set(monthly_draws["asset_id"])
    draw_assets = set(draws["asset_id"])
    if monthly_assets != draw_assets:
        raise ValueError("monthly and horizon retained draw asset sets must match")
    if monthly_assets != available_assets:
        raise ValueError(
            "retained draw asset coverage must equal available summary assets"
        )

    expected_draw_ids = set(range(config.draw_count))
    for asset_id in sorted(available_assets):
        monthly_ids = {
            _nonnegative_integer(value, name="monthly draw_id")
            for value in monthly_draws.loc[
                monthly_draws["asset_id"].eq(asset_id), "draw_id"
            ].tolist()
        }
        horizon_ids = {
            _nonnegative_integer(value, name="horizon draw_id")
            for value in draws.loc[draws["asset_id"].eq(asset_id), "draw_id"].tolist()
        }
        if monthly_ids != expected_draw_ids or horizon_ids != expected_draw_ids:
            raise ValueError(
                "available asset draw_id values must be exactly 0 through draw_count - 1"
            )


def _validate_result_frames(
    summary: pd.DataFrame,
    monthly_draws: pd.DataFrame,
    draws: pd.DataFrame,
    config: CurrentDistributionConfig,
) -> None:
    if monthly_draws.duplicated(["asset_id", "draw_id", "month_number"]).any():
        raise ValueError("monthly retained draw dimensions must be unique")
    if draws.duplicated(["asset_id", "draw_id", "horizon_months"]).any():
        raise ValueError("horizon retained draw dimensions must be unique")
    if summary.duplicated(["asset_id", "horizon_months", "return_basis"]).any():
        raise ValueError("summary dimensions must be unique")

    _validate_result_provenance(summary, monthly_draws, draws)
    _validate_asset_coverage(summary, monthly_draws, draws, config)

    if not monthly_draws.empty:
        monthly_values = monthly_draws[
            [
                "asset_monthly_return",
                "benchmark_monthly_return",
                "relative_monthly_return",
            ]
        ].to_numpy(dtype="float64")
        if not np.isfinite(monthly_values).all():
            raise ValueError("monthly retained draws must be finite")
        if bool(
            (
                monthly_draws[
                    ["asset_monthly_return", "benchmark_monthly_return"]
                ].to_numpy(dtype="float64")
                <= -1.0
            ).any()
        ):
            raise ValueError("monthly retained returns must be greater than -1 (-100%)")
        expected_relative = (1.0 + monthly_draws["asset_monthly_return"]) / (
            1.0 + monthly_draws["benchmark_monthly_return"]
        ) - 1.0
        if not np.allclose(
            monthly_draws["relative_monthly_return"],
            expected_relative,
            atol=1e-10,
            rtol=1e-10,
        ):
            raise ValueError("relative monthly returns are inconsistent")
        for _, group in monthly_draws.groupby(["asset_id", "draw_id"], sort=False):
            ordered = group.sort_values("month_number", kind="stable")
            if ordered["month_number"].tolist() != list(range(1, 13)):
                raise ValueError("monthly draws must retain one complete 12-month path")
            origin = pd.Timestamp(ordered["forecast_origin"].iloc[0])
            if set(ordered["forecast_origin"]) != {ordered["forecast_origin"].iloc[0]}:
                raise ValueError("forecast_origin must be constant within a path")
            if (
                pd.DatetimeIndex(ordered["date"]).tolist()
                != _future_dates(origin.date()).tolist()
            ):
                raise ValueError(
                    "monthly draw dates must be continuous future month-ends"
                )

    if not draws.empty and monthly_draws.empty:
        raise ValueError("horizon draws require retained monthly paths")
    for (asset_id, draw_id), group in draws.groupby(
        ["asset_id", "draw_id"], sort=False
    ):
        if set(group["horizon_months"]) != set(HORIZONS) or len(group) != 3:
            raise ValueError("horizon draws must retain 3/6/12 for every path")
        monthly = monthly_draws.loc[
            monthly_draws["asset_id"].eq(asset_id)
            & monthly_draws["draw_id"].eq(draw_id)
        ].sort_values("month_number", kind="stable")
        if len(monthly) != 12:
            raise ValueError("horizon draws do not align with monthly paths")
        for row in group.itertuples(index=False):
            prefix = monthly.iloc[: row.horizon_months]
            absolute = float(np.prod(1.0 + prefix["asset_monthly_return"]) - 1.0)
            benchmark = float(np.prod(1.0 + prefix["benchmark_monthly_return"]) - 1.0)
            excess = (1.0 + absolute) / (1.0 + benchmark) - 1.0
            relative_monthly = prefix["relative_monthly_return"].to_numpy()
            _close(row.absolute_return, absolute, name="absolute horizon draw")
            _close(row.benchmark_return, benchmark, name="benchmark horizon draw")
            _close(row.excess_return, excess, name="excess horizon draw")
            _close(
                row.absolute_max_drawdown,
                float(compute_max_drawdown(prefix["asset_monthly_return"].to_numpy())),
                name="absolute max drawdown",
            )
            _close(
                row.excess_max_drawdown,
                float(compute_max_drawdown(relative_monthly)),
                name="excess max drawdown",
            )

    probability_columns = (
        "raw_up_probability",
        "raw_neutral_probability",
        "raw_down_probability",
        "up_probability",
        "neutral_probability",
        "down_probability",
    )
    metric_columns = probability_columns + (
        "q10",
        "q25",
        "q50",
        "q75",
        "q90",
        "expected_return",
        "volatility",
        "var95",
        "cvar95",
        "drawdown_q50",
        "drawdown_q80",
        "drawdown_q95",
    )
    for asset_id, asset_summary in summary.groupby("asset_id", sort=False):
        if (
            set(asset_summary["horizon_months"]) != set(HORIZONS)
            or set(asset_summary["return_basis"]) != set(RETURN_BASES)
            or len(asset_summary) != 6
        ):
            raise ValueError("summary must retain absolute/excess rows for 3/6/12")
        asset_draws = draws.loc[draws["asset_id"].eq(asset_id)]
        expected_status = "available" if not asset_draws.empty else "unavailable"
        if set(asset_summary["status"]) != {expected_status}:
            raise ValueError("summary status is inconsistent with retained draws")
        if expected_status == "unavailable":
            if not asset_summary.loc[:, metric_columns].isna().all().all():
                raise ValueError("unavailable summary metrics must be missing")
            continue
        for row in asset_summary.itertuples(index=False):
            horizon_draws = asset_draws.loc[
                asset_draws["horizon_months"].eq(row.horizon_months)
            ]
            returns = horizon_draws[
                "absolute_return" if row.return_basis == "absolute" else "excess_return"
            ].to_numpy(dtype="float64")
            drawdowns = horizon_draws[
                "absolute_max_drawdown"
                if row.return_basis == "absolute"
                else "excess_max_drawdown"
            ].to_numpy(dtype="float64")
            raw = direction_probabilities(
                returns,
                neutral_band=config.neutral_bands[
                    (row.return_basis, row.horizon_months)
                ],
            )
            _close(row.raw_up_probability, raw["up"], name="summary raw up")
            _close(
                row.raw_neutral_probability,
                raw["neutral"],
                name="summary raw neutral",
            )
            _close(row.raw_down_probability, raw["down"], name="summary raw down")
            calibrated = np.asarray(
                [row.up_probability, row.neutral_probability, row.down_probability],
                dtype="float64",
            )
            if (
                not np.isfinite(calibrated).all()
                or bool(((calibrated < 0.0) | (calibrated > 1.0)).any())
                or not np.isclose(calibrated.sum(), 1.0, atol=1e-10, rtol=1e-10)
            ):
                raise ValueError("summary calibrated probabilities are invalid")
            if row.calibration_version == "identity-v1" and not np.allclose(
                calibrated,
                [raw["up"], raw["neutral"], raw["down"]],
                atol=1e-10,
                rtol=1e-10,
            ):
                raise ValueError("identity calibration must preserve raw probabilities")
            q10, q25, q50, q75, q90 = np.quantile(
                returns,
                [0.10, 0.25, 0.50, 0.75, 0.90],
            )
            for name, expected in (
                ("q10", q10),
                ("q25", q25),
                ("q50", q50),
                ("q75", q75),
                ("q90", q90),
                ("expected_return", np.mean(returns)),
            ):
                _close(getattr(row, name), float(expected), name=f"summary {name}")
            risk = summarize_risk(returns, drawdowns)
            for name in (
                "volatility",
                "var95",
                "cvar95",
                "drawdown_q50",
                "drawdown_q80",
                "drawdown_q95",
            ):
                _close(getattr(row, name), getattr(risk, name), name=f"summary {name}")


@dataclass(frozen=True)
class CurrentDistributionResult:
    """Detached retained paths and summaries hardened against forged aggregates."""

    summary: pd.DataFrame
    monthly_draws: pd.DataFrame
    draws: pd.DataFrame
    config: CurrentDistributionConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, CurrentDistributionConfig):
            raise TypeError("config must be a CurrentDistributionConfig")
        summary = _require_frame(
            object.__getattribute__(self, "summary"),
            name="summary",
            columns=CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
        )
        monthly_draws = _require_frame(
            object.__getattribute__(self, "monthly_draws"),
            name="monthly_draws",
            columns=CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
        )
        draws = _require_frame(
            object.__getattribute__(self, "draws"),
            name="draws",
            columns=CURRENT_DISTRIBUTION_DRAW_COLUMNS,
        )
        summary = summary.sort_values(
            ["asset_id", "horizon_months", "return_basis"],
            kind="stable",
        ).reset_index(drop=True)
        monthly_draws = monthly_draws.sort_values(
            ["asset_id", "draw_id", "month_number"],
            kind="stable",
        ).reset_index(drop=True)
        draws = draws.sort_values(
            ["asset_id", "draw_id", "horizon_months"],
            kind="stable",
        ).reset_index(drop=True)
        _validate_result_frames(summary, monthly_draws, draws, self.config)
        object.__setattr__(self, "summary", summary.copy(deep=True))
        object.__setattr__(self, "monthly_draws", monthly_draws.copy(deep=True))
        object.__setattr__(self, "draws", draws.copy(deep=True))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FRAME_FIELDS and isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        return value

    @property
    def retained_draws(self) -> pd.DataFrame:
        return self.draws


def estimate_current_distribution(
    *,
    snapshot: CurrentFeatureSnapshot,
    stage1: object,
    stage2: object,
    cycle_forecasts: pd.DataFrame,
    channel_residual_forecasts: pd.DataFrame,
    predictor_forecasts: pd.DataFrame | None,
    benchmark_forecasts: pd.DataFrame,
    residual_history: pd.DataFrame,
    config: CurrentDistributionConfig | None = None,
    calibrator: ProbabilityCalibrator | None = None,
) -> CurrentDistributionResult:
    """Generate absolute and relative 3/6/12-month joint path distributions."""

    if not isinstance(snapshot, CurrentFeatureSnapshot):
        raise TypeError("snapshot must be a CurrentFeatureSnapshot")
    if not isinstance(stage1, CycleToChannelResult):
        raise TypeError("stage1 must be a CycleToChannelResult")
    if not isinstance(stage2, ChannelToAssetResult):
        raise TypeError("stage2 must be a ChannelToAssetResult")
    normalized_config = config or CurrentDistributionConfig()
    if not isinstance(normalized_config, CurrentDistributionConfig):
        raise TypeError("config must be a CurrentDistributionConfig")
    normalized_calibrator: ProbabilityCalibrator = (
        IdentityProbabilityCalibrator() if calibrator is None else calibrator
    )
    calibration_version = _calibrator_version(normalized_calibrator)

    stage1_posteriors, stage1_date = _select_stage1(stage1, snapshot=snapshot)
    stage2_posteriors, stage2_date = _select_stage2(stage2, snapshot=snapshot)
    channels = tuple(sorted(stage1_posteriors))
    assets = tuple(sorted(stage2_posteriors))
    for posterior in stage2_posteriors.values():
        stage2_channels = {
            component_id
            for component_type, component_id in posterior.labels
            if component_type == "channel"
        }
        if not stage2_channels.issubset(stage1_posteriors):
            raise ValueError(
                "stage2 channel predictors must align with stage1 channels"
            )

    cycles, channel_residuals, predictors, benchmarks = _normalize_forecasts(
        snapshot=snapshot,
        config=normalized_config,
        channels=channels,
        assets=assets,
        stage2=stage2_posteriors,
        cycle_forecasts=cycle_forecasts,
        channel_residual_forecasts=channel_residual_forecasts,
        predictor_forecasts=predictor_forecasts,
        benchmark_forecasts=benchmark_forecasts,
    )
    histories = _normalize_residual_history(
        residual_history,
        snapshot=snapshot,
        assets=assets,
    )
    stage1_support = min(
        posterior.training_count for posterior in stage1_posteriors.values()
    )
    stage1_usable = all(posterior.usable for posterior in stage1_posteriors.values())
    supports: dict[str, _AssetSupport] = {}
    for asset_id in assets:
        stage2_posterior = stage2_posteriors[asset_id]
        residual_count = len(histories[asset_id])
        effective_samples = min(
            stage1_support,
            stage2_posterior.effective_training_count,
            residual_count,
        )
        available = (
            stage1_usable
            and stage2_posterior.usable
            and residual_count >= normalized_config.residual_block_length
            and effective_samples >= normalized_config.min_effective_samples
        )
        supports[asset_id] = _AssetSupport(
            effective_samples=effective_samples,
            stage1_training_count=stage1_support,
            stage2_effective_training_count=(stage2_posterior.effective_training_count),
            residual_history_count=residual_count,
            available=available,
        )

    dates = _future_dates(snapshot.as_of)
    cycle_values = _cube(
        cycles,
        labels=tuple(CYCLE_IDS),
        label_column="cycle_id",
        value_column="cycle_forecast",
        draw_count=normalized_config.draw_count,
        dates=dates,
    )
    channel_residual_values = _cube(
        channel_residuals,
        labels=channels,
        label_column="channel_id",
        value_column="channel_residual",
        draw_count=normalized_config.draw_count,
        dates=dates,
    )
    channel_paths: dict[str, np.ndarray] = {}
    for channel_position, channel_id in enumerate(channels):
        posterior = stage1_posteriors[channel_id]
        coefficients = _normal_draws(
            posterior.mean,
            posterior.covariance,
            draw_count=normalized_config.draw_count,
            generator=_rng(
                normalized_config.seed,
                snapshot.provenance.run_id,
                "stage1",
                channel_id,
            ),
        )
        channel_paths[channel_id] = (
            posterior.intercept
            + np.einsum("dc,dtc->dt", coefficients, cycle_values)
            + channel_residual_values[:, :, channel_position]
        )

    monthly_records: list[dict[str, object]] = []
    draw_records: list[dict[str, object]] = []
    for asset_id in assets:
        support = supports[asset_id]
        if not support.available:
            continue
        posterior = stage2_posteriors[asset_id]
        coefficients = _normal_draws(
            posterior.mean,
            posterior.covariance,
            draw_count=normalized_config.draw_count,
            generator=_rng(
                normalized_config.seed,
                snapshot.provenance.run_id,
                "stage2",
                asset_id,
            ),
        )
        benchmark_values = _asset_matrix(
            benchmarks,
            asset_id=asset_id,
            value_column="benchmark_return",
            draw_count=normalized_config.draw_count,
            dates=dates,
        )
        design = np.zeros(
            (normalized_config.draw_count, 12, len(posterior.labels)),
            dtype="float64",
        )
        for position, (component_type, component_id) in enumerate(posterior.labels):
            if component_type == "intercept":
                design[:, :, position] = 1.0
            elif component_type == "benchmark":
                design[:, :, position] = benchmark_values
            elif component_type == "channel":
                design[:, :, position] = channel_paths[component_id]
            else:
                design[:, :, position] = _predictor_matrix(
                    predictors,
                    asset_id=asset_id,
                    component_type=component_type,
                    component_id=component_id,
                    draw_count=normalized_config.draw_count,
                    dates=dates,
                )
        residual_paths = _bootstrap_paths(
            histories[asset_id],
            config=normalized_config,
            generator=_rng(
                normalized_config.seed,
                snapshot.provenance.run_id,
                "residual",
                asset_id,
            ),
        )
        asset_values = np.einsum("dp,dtp->dt", coefficients, design) + residual_paths
        if bool((asset_values <= -1.0).any()):
            raise ValueError("asset monthly returns must be greater than -1 (-100%)")
        if bool((benchmark_values <= -1.0).any()):
            raise ValueError(
                "benchmark monthly returns must be greater than -1 (-100%)"
            )
        relative_values = (1.0 + asset_values) / (1.0 + benchmark_values) - 1.0
        for draw_id in range(normalized_config.draw_count):
            for month_position, forecast_date in enumerate(dates):
                monthly_records.append(
                    {
                        "asset_id": asset_id,
                        "draw_id": draw_id,
                        "month_number": month_position + 1,
                        "date": forecast_date,
                        "forecast_origin": snapshot.as_of,
                        "asset_monthly_return": asset_values[draw_id, month_position],
                        "benchmark_monthly_return": benchmark_values[
                            draw_id, month_position
                        ],
                        "relative_monthly_return": relative_values[
                            draw_id, month_position
                        ],
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                    }
                )
        for horizon in HORIZONS:
            asset_prefix = asset_values[:, :horizon]
            benchmark_prefix = benchmark_values[:, :horizon]
            relative_prefix = relative_values[:, :horizon]
            absolute_returns = np.prod(1.0 + asset_prefix, axis=1) - 1.0
            benchmark_returns = np.prod(1.0 + benchmark_prefix, axis=1) - 1.0
            excess_returns = (1.0 + absolute_returns) / (1.0 + benchmark_returns) - 1.0
            absolute_drawdowns = compute_max_drawdown(asset_prefix)
            excess_drawdowns = compute_max_drawdown(relative_prefix)
            for draw_id in range(normalized_config.draw_count):
                draw_records.append(
                    {
                        "asset_id": asset_id,
                        "draw_id": draw_id,
                        "horizon_months": horizon,
                        "absolute_return": absolute_returns[draw_id],
                        "benchmark_return": benchmark_returns[draw_id],
                        "excess_return": excess_returns[draw_id],
                        "absolute_max_drawdown": absolute_drawdowns[draw_id],
                        "excess_max_drawdown": excess_drawdowns[draw_id],
                        "run_id": snapshot.provenance.run_id,
                        "snapshot_as_of": snapshot.as_of,
                    }
                )

    monthly_frame = pd.DataFrame(
        monthly_records,
        columns=CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS,
    )
    draw_frame = pd.DataFrame(
        draw_records,
        columns=CURRENT_DISTRIBUTION_DRAW_COLUMNS,
    )
    summary_frame = pd.DataFrame(
        _summary_records(
            assets=assets,
            draws=draw_frame,
            supports=supports,
            config=normalized_config,
            calibrator=normalized_calibrator,
            calibration_version=calibration_version,
            snapshot=snapshot,
            stage1_date=stage1_date,
            stage2_date=stage2_date,
        ),
        columns=CURRENT_DISTRIBUTION_SUMMARY_COLUMNS,
    )
    return CurrentDistributionResult(
        summary=summary_frame,
        monthly_draws=monthly_frame,
        draws=draw_frame,
        config=normalized_config,
    )


__all__ = [
    "BENCHMARK_FORECAST_COLUMNS",
    "CHANNEL_RESIDUAL_FORECAST_COLUMNS",
    "CURRENT_DISTRIBUTION_DRAW_COLUMNS",
    "CURRENT_DISTRIBUTION_MONTHLY_DRAW_COLUMNS",
    "CURRENT_DISTRIBUTION_SUMMARY_COLUMNS",
    "CYCLE_FORECAST_COLUMNS",
    "PREDICTOR_FORECAST_COLUMNS",
    "RESIDUAL_HISTORY_COLUMNS",
    "CurrentDistributionConfig",
    "CurrentDistributionResult",
    "IdentityProbabilityCalibrator",
    "ProbabilityCalibrator",
    "direction_probabilities",
    "estimate_current_distribution",
]
