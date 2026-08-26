"""Deterministic uncertainty intervals for conserved asset attribution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import hashlib
from numbers import Integral, Real
from typing import Iterable

import numpy as np
import pandas as pd

from seven_cycle_platform.attribution.stage1 import CYCLE_IDS


ATTRIBUTION_INTERVAL_COLUMNS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
    "component_type",
    "component_id",
    "point_contribution",
    "lower_50",
    "upper_50",
    "lower_80",
    "upper_80",
    "interval_status",
    "significance",
    "effective_samples",
    "draw_count",
    "status",
    "evidence_level",
    "observed_return",
    "reconstructed_return",
    "is_explained",
    "is_residual",
)

ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
    "point_component_sum",
    "observed_return",
    "point_conservation_error",
    "max_draw_conservation_error",
    "available_component_count",
    "unavailable_component_count",
    "status",
)

ATTRIBUTION_DRAW_COLUMNS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
    "draw",
    "component_type",
    "component_id",
    "contribution",
    "target_return",
)

CYCLE_UNCERTAINTY_COLUMNS = (
    "date",
    "cycle_id",
    "uncertainty",
)

CHANNEL_UNCERTAINTY_COLUMNS = (
    "date",
    "channel_id",
    "uncertainty",
)

_RESULT_FIELDS = frozenset({"intervals", "diagnostics", "draws"})
_VALID_RETURN_BASES = frozenset({"absolute", "excess"})
_USABLE_STAGE2_STATUSES = frozenset({"estimated", "parent_informed", "parent_only"})
_FAILED_STATUSES = frozenset(
    {"insufficient_history", "not_identifiable", "unavailable"}
)
_VALID_INTERVAL_STATUSES = frozenset({"available", "degraded", "unavailable"})
_VALID_SIGNIFICANCE = frozenset(
    {"positive", "negative", "not_significant", "unavailable"}
)
_VALID_EVIDENCE = frozenset({"high", "medium", "low"})
_VALID_DIAGNOSTIC_STATUSES = frozenset({"available", "partial", "unavailable"})
_GROUP_DIMENSIONS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
)
_INTERVAL_DIMENSIONS = (*_GROUP_DIMENSIONS, "component_type", "component_id")
_COMPONENT_ORDER = {
    "asset_intercept": 0,
    "benchmark": 1,
    "cycle": 2,
    "cycle_group": 3,
    "channel_baseline_path": 4,
    "channel_residual_path": 5,
    "unresolved_channel": 6,
    "interaction": 7,
    "control": 8,
    "event": 9,
    "unobserved_channel_residual": 10,
    "asset_residual": 11,
}


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Integral, np.integer)
    ):
        raise TypeError(f"{name} must be a positive integer")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Integral, np.integer)
    ):
        raise TypeError(f"{name} must be a nonnegative integer")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return normalized


def _positive_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (Real, np.integer, np.floating)
    ):
        raise TypeError(f"{name} must be a positive finite real number")
    normalized = float(value)
    if not np.isfinite(normalized) or normalized <= 0.0:
        raise ValueError(f"{name} must be a positive finite real number")
    return normalized


def _strict_bool(value: object, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be boolean")
    return bool(value)


@dataclass(frozen=True)
class UncertaintyConfig:
    """Controls seeded Monte Carlo and past-only residual block bootstrap."""

    draw_count: int = 2_000
    seed: int = 0
    block_length: int = 3
    min_effective_samples: int = 12
    conservation_tolerance: float = 1e-10
    enable_cycle_state: bool = True
    enable_stage1_covariance: bool = True
    enable_stage2_covariance: bool = True
    enable_channel_uncertainty: bool = True
    enable_residual_bootstrap: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "draw_count", _positive_integer(self.draw_count, "draw_count")
        )
        object.__setattr__(self, "seed", _nonnegative_integer(self.seed, "seed"))
        object.__setattr__(
            self,
            "block_length",
            _positive_integer(self.block_length, "block_length"),
        )
        object.__setattr__(
            self,
            "min_effective_samples",
            _positive_integer(self.min_effective_samples, "min_effective_samples"),
        )
        object.__setattr__(
            self,
            "conservation_tolerance",
            _positive_real(self.conservation_tolerance, "conservation_tolerance"),
        )
        for field_name in (
            "enable_cycle_state",
            "enable_stage1_covariance",
            "enable_stage2_covariance",
            "enable_channel_uncertainty",
            "enable_residual_bootstrap",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_bool(getattr(self, field_name), field_name),
            )


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


@dataclass(frozen=True)
class AttributionIntervalResult:
    """Detached interval rows, conservation diagnostics, and optional draws."""

    intervals: pd.DataFrame
    diagnostics: pd.DataFrame
    draws: pd.DataFrame
    draw_count: int
    seed: int

    def __post_init__(self) -> None:
        intervals = object.__getattribute__(self, "intervals")
        diagnostics = object.__getattribute__(self, "diagnostics")
        draws = object.__getattribute__(self, "draws")
        for values, columns, name in (
            (intervals, ATTRIBUTION_INTERVAL_COLUMNS, "intervals"),
            (
                diagnostics,
                ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
                "diagnostics",
            ),
            (draws, ATTRIBUTION_DRAW_COLUMNS, "draws"),
        ):
            if not isinstance(values, pd.DataFrame):
                raise TypeError(f"{name} must be a pandas DataFrame")
            if tuple(values.columns) != columns:
                raise ValueError(
                    f"{name} columns do not match the uncertainty contract"
                )
        object.__setattr__(
            self,
            "draw_count",
            _positive_integer(
                object.__getattribute__(self, "draw_count"), "draw_count"
            ),
        )
        object.__setattr__(
            self,
            "seed",
            _nonnegative_integer(object.__getattribute__(self, "seed"), "seed"),
        )
        _validate_interval_result_frames(
            intervals,
            diagnostics,
            draws,
            draw_count=object.__getattribute__(self, "draw_count"),
        )
        object.__setattr__(self, "intervals", _copy_frame(intervals))
        object.__setattr__(self, "diagnostics", _copy_frame(diagnostics))
        object.__setattr__(self, "draws", _copy_frame(draws))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    @property
    def frame(self) -> pd.DataFrame:
        return self.intervals


@dataclass(frozen=True)
class _ContributionFrames:
    components: pd.DataFrame
    paths: pd.DataFrame


def _normalize_date(value: object, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_, Real, np.integer, np.floating)):
        raise TypeError(f"{name} must be date-like")
    if not isinstance(value, (date, datetime, np.datetime64, pd.Timestamp, str)):
        raise TypeError(f"{name} must be date-like")
    try:
        normalized = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(normalized):
        raise ValueError(f"{name} cannot be missing")
    if normalized.tzinfo is not None:
        raise ValueError(f"{name} must be timezone-naive")
    return normalized.normalize()


def _normalize_dates(values: pd.Series, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_date(value, name) for value in values.tolist()],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _source_frame(values: object, attribute: str, name: str) -> pd.DataFrame:
    if isinstance(values, pd.DataFrame):
        return values.copy(deep=True)
    frame = getattr(values, attribute, None)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame or expose .{attribute}")
    return frame.copy(deep=True)


def _required_columns(
    values: pd.DataFrame,
    columns: Iterable[str],
    name: str,
) -> pd.DataFrame:
    if values.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")
    return values.copy(deep=True)


def _normalize_identifier_columns(values: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if any(
            not isinstance(value, str) or not value for value in values[column].tolist()
        ):
            raise TypeError(f"{column} values must be non-empty strings")


def _normalize_numeric_column(
    values: pd.Series,
    name: str,
    *,
    allow_missing: bool,
    nonnegative: bool = False,
) -> pd.Series:
    normalized: list[float] = []
    for value in values.tolist():
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            if allow_missing:
                normalized.append(np.nan)
                continue
            raise ValueError(f"{name} values cannot be missing")
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (Real, np.integer, np.floating)
        ):
            raise TypeError(f"{name} values must be numeric")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"{name} values must be finite")
        if nonnegative and numeric < 0.0:
            raise ValueError(f"{name} values must be nonnegative")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _normalize_count_column(
    values: pd.Series,
    name: str,
    *,
    positive: bool,
) -> pd.Series:
    normalized: list[int] = []
    minimum = 1 if positive else 0
    qualifier = "positive" if positive else "nonnegative"
    for value in values.tolist():
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (Integral, np.integer)
        ):
            raise TypeError(f"{name} values must be {qualifier} integers")
        numeric = int(value)
        if numeric < minimum:
            raise ValueError(f"{name} values must be {qualifier} integers")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="int64")


def _normalize_support_column(values: pd.Series, name: str) -> pd.Series:
    normalized: list[int] = []
    for value in values.tolist():
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (Real, np.integer, np.floating)
        ):
            raise TypeError(f"{name} values must be nonnegative finite numbers")
        numeric = float(value)
        if not np.isfinite(numeric) or numeric < 0.0:
            raise ValueError(f"{name} values must be nonnegative finite numbers")
        normalized.append(int(np.floor(numeric)))
    return pd.Series(normalized, index=values.index, dtype="int64")


def _normalize_contribution_result(
    values: object,
    tolerance: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    components = _source_frame(values, "components", "contribution_result")
    paths = _source_frame(values, "paths", "contribution_result")
    components = _required_columns(
        components,
        (
            "date",
            "asset_id",
            "component_type",
            "component_id",
            "contribution",
            "observed_return",
            "reconstructed_return",
            "is_explained",
            "is_residual",
            "status",
        ),
        "contribution components",
    )
    paths = _required_columns(
        paths,
        (
            "date",
            "asset_id",
            "channel_id",
            "cycle_id",
            "allocation_group_id",
            "stage1_status",
            "stage2_status",
        ),
        "contribution paths",
    )
    components["date"] = _normalize_dates(components["date"], "component date")
    paths["date"] = _normalize_dates(paths["date"], "path date")
    _normalize_identifier_columns(
        components,
        ("asset_id", "component_type", "component_id", "status"),
    )
    _normalize_identifier_columns(
        paths,
        (
            "asset_id",
            "channel_id",
            "cycle_id",
            "allocation_group_id",
            "stage1_status",
            "stage2_status",
        ),
    )
    components["contribution"] = _normalize_numeric_column(
        components["contribution"], "contribution", allow_missing=False
    )
    for column in ("observed_return", "reconstructed_return"):
        components[column] = _normalize_numeric_column(
            components[column], column, allow_missing=False
        )
    if components.duplicated(
        ["date", "asset_id", "component_type", "component_id"]
    ).any():
        raise ValueError("contribution component rows must be unique")
    if paths.duplicated(["date", "asset_id", "channel_id", "cycle_id"]).any():
        raise ValueError("contribution path rows must be unique")
    for column in ("is_explained", "is_residual"):
        if any(
            not isinstance(value, (bool, np.bool_))
            for value in components[column].tolist()
        ):
            raise TypeError(f"{column} values must be boolean")
        components[column] = components[column].astype("bool")
    for _, group in components.groupby(["date", "asset_id"], sort=False):
        observed = float(group["observed_return"].iloc[0])
        reconstructed = float(group["reconstructed_return"].iloc[0])
        if not np.allclose(
            group["observed_return"], observed, atol=tolerance, rtol=0.0
        ):
            raise ValueError("observed_return must be constant within an asset group")
        if not np.allclose(
            group["reconstructed_return"], reconstructed, atol=tolerance, rtol=0.0
        ):
            raise ValueError(
                "reconstructed_return must be constant within an asset group"
            )
        if not np.isclose(
            float(group["contribution"].sum()), observed, atol=tolerance, rtol=0.0
        ):
            raise ValueError(
                "point component contributions must conserve observed_return"
            )
        if not np.isclose(reconstructed, observed, atol=tolerance, rtol=0.0):
            raise ValueError("point reconstructed_return must equal observed_return")
    components["_component_order"] = components["component_type"].map(_COMPONENT_ORDER)
    if components["_component_order"].isna().any():
        raise ValueError("unknown contribution component_type")
    components = (
        components.sort_values(
            ["date", "asset_id", "_component_order", "component_id"],
            kind="stable",
        )
        .drop(columns="_component_order")
        .reset_index(drop=True)
    )
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    paths["_cycle_order"] = paths["cycle_id"].map(cycle_order)
    if paths["_cycle_order"].isna().any():
        raise ValueError("contribution paths contain an unknown cycle_id")
    paths = (
        paths.sort_values(
            ["date", "asset_id", "channel_id", "_cycle_order"],
            kind="stable",
        )
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )
    return components, paths


def _normalize_stage1_paths(values: object) -> pd.DataFrame:
    frame = _source_frame(values, "paths", "stage1_paths")
    required = (
        "date",
        "channel_id",
        "cycle_id",
        "cycle_innovation",
        "coefficient_mean",
        "intercept",
        "channel_residual",
        "training_count",
        "status",
    )
    frame = _required_columns(frame, required, "stage1_paths").loc[:, required]
    frame["date"] = _normalize_dates(frame["date"], "stage1 date")
    _normalize_identifier_columns(frame, ("channel_id", "cycle_id", "status"))
    for column in (
        "cycle_innovation",
        "coefficient_mean",
        "intercept",
        "channel_residual",
    ):
        frame[column] = _normalize_numeric_column(
            frame[column], column, allow_missing=True
        )
    frame["training_count"] = _normalize_count_column(
        frame["training_count"], "training_count", positive=False
    )
    if frame.duplicated(["date", "channel_id", "cycle_id"]).any():
        raise ValueError("stage1 date × channel × cycle rows must be unique")
    cycle_order = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
    frame["_cycle_order"] = frame["cycle_id"].map(cycle_order)
    if frame["_cycle_order"].isna().any():
        raise ValueError("stage1_paths contain an unknown cycle_id")
    return (
        frame.sort_values(["date", "channel_id", "_cycle_order"], kind="stable")
        .drop(columns="_cycle_order")
        .reset_index(drop=True)
    )


def _normalize_stage2_components(values: object) -> pd.DataFrame:
    frame = _source_frame(values, "components", "stage2_components")
    required = (
        "date",
        "asset_id",
        "component_type",
        "component_id",
        "component_value",
        "coefficient_mean",
        "training_count",
        "effective_training_count",
        "status",
    )
    frame = _required_columns(frame, required, "stage2_components").loc[:, required]
    frame["date"] = _normalize_dates(frame["date"], "stage2 date")
    _normalize_identifier_columns(
        frame, ("asset_id", "component_type", "component_id", "status")
    )
    for column in ("component_value", "coefficient_mean"):
        frame[column] = _normalize_numeric_column(
            frame[column], column, allow_missing=True
        )
    frame["effective_training_count"] = _normalize_support_column(
        frame["effective_training_count"],
        "effective_training_count",
    )
    frame["training_count"] = _normalize_count_column(
        frame["training_count"], "training_count", positive=False
    )
    if bool((frame["effective_training_count"] > frame["training_count"]).any()):
        raise ValueError("effective_training_count cannot exceed training_count")
    if frame.duplicated(["date", "asset_id", "component_type", "component_id"]).any():
        raise ValueError("stage2 component rows must be unique")
    return frame.sort_values(
        ["date", "asset_id", "component_type", "component_id"], kind="stable"
    ).reset_index(drop=True)


def _normalize_covariance(
    values: object | None,
    *,
    attribute: str,
    name: str,
    required: tuple[str, ...],
    dimensions: tuple[str, ...],
    support_column: str,
) -> pd.DataFrame:
    if values is None:
        return pd.DataFrame(columns=required)
    frame = _source_frame(values, attribute, name)
    frame = _required_columns(frame, required, name).loc[:, required]
    frame["date"] = _normalize_dates(frame["date"], f"{name} date")
    identifier_columns = [
        column
        for column in required
        if column
        not in {
            "date",
            "coefficient_covariance",
            support_column,
            "training_count",
        }
    ]
    _normalize_identifier_columns(frame, identifier_columns)
    frame["coefficient_covariance"] = _normalize_numeric_column(
        frame["coefficient_covariance"],
        "coefficient_covariance",
        allow_missing=True,
    )
    frame[support_column] = (
        _normalize_count_column(frame[support_column], support_column, positive=False)
        if support_column == "training_count"
        else _normalize_support_column(frame[support_column], support_column)
    )
    if "training_count" in frame and support_column != "training_count":
        frame["training_count"] = _normalize_count_column(
            frame["training_count"], "training_count", positive=False
        )
        if bool((frame[support_column] > frame["training_count"]).any()):
            raise ValueError("effective_training_count cannot exceed training_count")
    if frame.duplicated(list(dimensions)).any():
        raise ValueError(f"{name} rows must be unique")
    return frame.sort_values(list(dimensions), kind="stable").reset_index(drop=True)


def _normalize_uncertainty(
    values: object | None,
    *,
    id_column: str,
    name: str,
) -> pd.DataFrame:
    required = (
        CYCLE_UNCERTAINTY_COLUMNS
        if id_column == "cycle_id"
        else CHANNEL_UNCERTAINTY_COLUMNS
    )
    if values is None:
        return pd.DataFrame(columns=required)
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    frame = _required_columns(values, required, name).loc[:, required]
    frame["date"] = _normalize_dates(frame["date"], f"{name} date")
    _normalize_identifier_columns(frame, (id_column,))
    frame["uncertainty"] = _normalize_numeric_column(
        frame["uncertainty"], "uncertainty", allow_missing=True, nonnegative=True
    )
    if frame.duplicated(["date", id_column]).any():
        raise ValueError(f"{name} date × {id_column} rows must be unique")
    return frame.sort_values(["date", id_column], kind="stable").reset_index(drop=True)


def _normalize_residual_history(values: object | None) -> pd.DataFrame:
    columns = ("date", "asset_id", "component_type", "component_id", "value")
    if values is None:
        return pd.DataFrame(columns=columns)
    if not isinstance(values, pd.DataFrame):
        raise TypeError("residual_history must be a pandas DataFrame")
    required = ("date", "asset_id", "component_type", "component_id")
    frame = _required_columns(values, required, "residual_history")
    value_columns = [column for column in ("residual", "value") if column in frame]
    if not value_columns:
        raise ValueError("residual_history requires residual or value")
    source_column = "residual" if "residual" in value_columns else "value"
    frame = frame.loc[:, [*required, source_column]].rename(
        columns={source_column: "value"}
    )
    frame["date"] = _normalize_dates(frame["date"], "residual history date")
    _normalize_identifier_columns(frame, ("asset_id", "component_type", "component_id"))
    frame["value"] = _normalize_numeric_column(
        frame["value"], "residual history", allow_missing=False
    )
    if frame.duplicated(list(required)).any():
        raise ValueError("residual history rows must be unique")
    return frame.sort_values(list(required), kind="stable").reset_index(drop=True)


def _matrix_sqrt(matrix: np.ndarray) -> np.ndarray | None:
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        return None
    if not np.isfinite(matrix).all():
        return None
    symmetric = (matrix + matrix.T) / 2.0
    if not np.allclose(matrix, matrix.T, atol=1e-10, rtol=1e-10):
        return None
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    if float(eigenvalues.min()) < -1e-10 * scale:
        return None
    clipped = np.clip(eigenvalues, 0.0, None)
    return eigenvectors @ np.diag(np.sqrt(clipped))


def _long_covariance_matrix(
    frame: pd.DataFrame,
    labels: tuple[object, ...],
    *,
    row_columns: tuple[str, ...],
    column_columns: tuple[str, ...],
) -> np.ndarray | None:
    label_set = set(labels)
    lookup: dict[tuple[object, object], float] = {}
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
            value = getattr(row, "coefficient_covariance")
            if pd.isna(value):
                return None
            lookup[(row_label, column_label)] = float(value)
    expected = {(left, right) for left in labels for right in labels}
    if set(lookup) != expected:
        return None
    matrix = np.asarray(
        [[lookup[(left, right)] for right in labels] for left in labels],
        dtype="float64",
    )
    return matrix if _matrix_sqrt(matrix) is not None else None


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
    if square_root is None:
        raise ValueError("covariance is not positive semidefinite")
    standard = generator.standard_normal((draw_count, len(mean)))
    return mean + standard @ square_root.T


def _bootstrap_noise(
    history: np.ndarray,
    *,
    horizon_months: int,
    config: UncertaintyConfig,
    generator: np.random.Generator,
) -> np.ndarray:
    centered = history - float(np.mean(history))
    maximum_start = len(centered) - config.block_length
    draws = np.zeros(config.draw_count, dtype="float64")
    for draw_position in range(config.draw_count):
        sampled: list[float] = []
        while len(sampled) < horizon_months:
            start = int(generator.integers(0, maximum_start + 1))
            sampled.extend(
                centered[start : start + config.block_length].astype("float64").tolist()
            )
        draws[draw_position] = float(sum(sampled[:horizon_months]))
    return draws


def _bootstrap_noise_path(
    history: np.ndarray,
    *,
    horizon_months: int,
    config: UncertaintyConfig,
    generator: np.random.Generator,
    valid_starts: np.ndarray,
) -> np.ndarray:
    centered = history - float(np.mean(history))
    paths = np.zeros(
        (config.draw_count, horizon_months),
        dtype="float64",
    )
    for draw_position in range(config.draw_count):
        sampled: list[float] = []
        while len(sampled) < horizon_months:
            start = int(valid_starts[generator.integers(0, len(valid_starts))])
            sampled.extend(
                centered[start : start + config.block_length].astype("float64").tolist()
            )
        paths[draw_position] = sampled[:horizon_months]
    return paths


def _significance(lower_80: float, upper_80: float) -> str:
    if lower_80 > 0.0:
        return "positive"
    if upper_80 < 0.0:
        return "negative"
    return "not_significant"


def _evidence_level(
    *,
    available: bool,
    degraded: bool,
    effective_samples: int,
    minimum: int,
) -> str:
    if not available or degraded or effective_samples < minimum:
        return "low"
    if effective_samples >= 2 * minimum:
        return "high"
    return "medium"


def _validate_interval_result_frames(
    intervals: pd.DataFrame,
    diagnostics: pd.DataFrame,
    draws: pd.DataFrame,
    *,
    draw_count: int,
    tolerance: float = 1e-10,
) -> None:
    if intervals.empty:
        raise ValueError("intervals must contain at least one row")
    if diagnostics.empty:
        raise ValueError("diagnostics must contain at least one row")
    normalized_intervals = intervals.copy(deep=True)
    normalized_diagnostics = diagnostics.copy(deep=True)
    normalized_draws = draws.copy(deep=True)
    for frame, name in (
        (normalized_intervals, "intervals"),
        (normalized_diagnostics, "diagnostics"),
        (normalized_draws, "draws"),
    ):
        if frame.columns.has_duplicates:
            raise ValueError(f"{name} columns must be unique")
    for column in ("period_start", "period_end"):
        normalized_intervals[column] = _normalize_dates(
            normalized_intervals[column], column
        )
        normalized_diagnostics[column] = _normalize_dates(
            normalized_diagnostics[column], column
        )
        if not normalized_draws.empty:
            normalized_draws[column] = _normalize_dates(
                normalized_draws[column], column
            )
    _normalize_identifier_columns(
        normalized_intervals,
        (
            "asset_id",
            "return_basis",
            "component_type",
            "component_id",
            "interval_status",
            "significance",
            "status",
            "evidence_level",
        ),
    )
    _normalize_identifier_columns(
        normalized_diagnostics, ("asset_id", "return_basis", "status")
    )
    if not normalized_draws.empty:
        _normalize_identifier_columns(
            normalized_draws,
            ("asset_id", "return_basis", "component_type", "component_id"),
        )
    for frame in (normalized_intervals, normalized_diagnostics):
        frame["horizon_months"] = _normalize_count_column(
            frame["horizon_months"], "horizon_months", positive=True
        )
    for column in ("available_component_count", "unavailable_component_count"):
        normalized_diagnostics[column] = _normalize_count_column(
            normalized_diagnostics[column], column, positive=False
        )
    for column in (
        "point_component_sum",
        "observed_return",
        "point_conservation_error",
    ):
        normalized_diagnostics[column] = _normalize_numeric_column(
            normalized_diagnostics[column], column, allow_missing=False
        )
    normalized_diagnostics["max_draw_conservation_error"] = _normalize_numeric_column(
        normalized_diagnostics["max_draw_conservation_error"],
        "max_draw_conservation_error",
        allow_missing=True,
    )
    if not set(normalized_diagnostics["return_basis"]).issubset(_VALID_RETURN_BASES):
        raise ValueError("diagnostic return_basis contains an unknown value")
    if not set(normalized_diagnostics["status"]).issubset(_VALID_DIAGNOSTIC_STATUSES):
        raise ValueError("diagnostic status contains an unknown value")
    if bool(
        (normalized_diagnostics["point_conservation_error"] < 0.0).any()
        or (normalized_diagnostics["max_draw_conservation_error"].dropna() < 0.0).any()
    ):
        raise ValueError("diagnostic conservation errors must be nonnegative")
    normalized_intervals["effective_samples"] = _normalize_count_column(
        normalized_intervals["effective_samples"],
        "effective_samples",
        positive=False,
    )
    normalized_intervals["draw_count"] = _normalize_count_column(
        normalized_intervals["draw_count"], "draw_count", positive=True
    )
    if (
        normalized_intervals["draw_count"].nunique() != 1
        or not normalized_intervals["draw_count"].eq(draw_count).all()
    ):
        raise ValueError(
            "interval draw_count must be constant and match result.draw_count"
        )
    for column in (
        "point_contribution",
        "observed_return",
        "reconstructed_return",
    ):
        normalized_intervals[column] = _normalize_numeric_column(
            normalized_intervals[column], column, allow_missing=False
        )
    for column in ("lower_50", "upper_50", "lower_80", "upper_80"):
        normalized_intervals[column] = _normalize_numeric_column(
            normalized_intervals[column], column, allow_missing=True
        )
    for column in ("is_explained", "is_residual"):
        if any(
            not isinstance(value, (bool, np.bool_))
            for value in normalized_intervals[column].tolist()
        ):
            raise TypeError(f"{column} values must be boolean")
    if not set(normalized_intervals["return_basis"]).issubset(_VALID_RETURN_BASES):
        raise ValueError("return_basis contains an unknown value")
    if not set(normalized_intervals["interval_status"]).issubset(
        _VALID_INTERVAL_STATUSES
    ):
        raise ValueError("interval_status contains an unknown value")
    if not set(normalized_intervals["significance"]).issubset(_VALID_SIGNIFICANCE):
        raise ValueError("significance contains an unknown value")
    if not set(normalized_intervals["evidence_level"]).issubset(_VALID_EVIDENCE):
        raise ValueError("evidence_level contains an unknown value")
    if normalized_intervals.duplicated(list(_INTERVAL_DIMENSIONS)).any():
        raise ValueError("interval dimensions must be unique")
    if normalized_diagnostics.duplicated(list(_GROUP_DIMENSIONS)).any():
        raise ValueError("diagnostic dimensions must be unique")
    if bool(
        (
            normalized_intervals["period_start"] > normalized_intervals["period_end"]
        ).any()
        or (
            normalized_diagnostics["period_start"]
            > normalized_diagnostics["period_end"]
        ).any()
    ):
        raise ValueError("period_start cannot be later than period_end")
    for row in normalized_intervals.itertuples(index=False):
        bounds = np.asarray(
            [row.lower_50, row.upper_50, row.lower_80, row.upper_80],
            dtype="float64",
        )
        if row.interval_status == "unavailable":
            if not np.isnan(bounds).all():
                raise ValueError("unavailable intervals require all bounds to be NaN")
            if row.significance != "unavailable" or row.evidence_level != "low":
                raise ValueError(
                    "unavailable intervals require unavailable significance and low evidence"
                )
        else:
            if not np.isfinite(bounds).all():
                raise ValueError("available intervals require finite bounds")
            if not row.lower_80 <= row.lower_50 <= row.upper_50 <= row.upper_80:
                raise ValueError("interval bounds must be nested")
            expected_significance = _significance(row.lower_80, row.upper_80)
            if row.significance != expected_significance:
                raise ValueError("significance must match the 80% interval")
            if row.interval_status == "degraded" and row.evidence_level != "low":
                raise ValueError("degraded intervals require low evidence")
            if row.status in _FAILED_STATUSES and row.interval_status == "available":
                raise ValueError(
                    "failed attribution status cannot publish an available interval"
                )
    diagnostic_lookup = {
        tuple(getattr(row, column) for column in _GROUP_DIMENSIONS): row
        for row in normalized_diagnostics.itertuples(index=False)
    }
    interval_groups = {
        key if isinstance(key, tuple) else (key,): group
        for key, group in normalized_intervals.groupby(
            list(_GROUP_DIMENSIONS), sort=False
        )
    }
    if set(diagnostic_lookup) != set(interval_groups):
        raise ValueError("interval and diagnostic groups must align exactly")
    for key, group in interval_groups.items():
        diagnostic = diagnostic_lookup[key]
        observed = float(group["observed_return"].iloc[0])
        reconstructed = float(group["reconstructed_return"].iloc[0])
        if not np.allclose(
            group["observed_return"], observed, atol=tolerance, rtol=0.0
        ) or not np.allclose(
            group["reconstructed_return"], reconstructed, atol=tolerance, rtol=0.0
        ):
            raise ValueError("grouped returns must be constant")
        point_sum = float(group["point_contribution"].sum())
        if not np.isclose(point_sum, observed, atol=tolerance, rtol=0.0):
            raise ValueError("point contributions must conserve observed_return")
        if not np.isclose(reconstructed, observed, atol=tolerance, rtol=0.0):
            raise ValueError("reconstructed_return must equal observed_return")
        available_count = int(group["interval_status"].ne("unavailable").sum())
        unavailable_count = len(group) - available_count
        expected_status = (
            "available"
            if unavailable_count == 0
            else "unavailable"
            if available_count == 0
            else "partial"
        )
        expected_error = abs(point_sum - observed)
        if not np.isclose(
            diagnostic.point_component_sum, point_sum, atol=tolerance, rtol=0.0
        ) or not np.isclose(
            diagnostic.observed_return, observed, atol=tolerance, rtol=0.0
        ):
            raise ValueError("diagnostic point values do not match intervals")
        if not np.isclose(
            diagnostic.point_conservation_error,
            expected_error,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("diagnostic point conservation error is inconsistent")
        if (
            diagnostic.available_component_count != available_count
            or diagnostic.unavailable_component_count != unavailable_count
            or diagnostic.status != expected_status
        ):
            raise ValueError(
                "diagnostic availability counts or status are inconsistent"
            )
        draw_error = diagnostic.max_draw_conservation_error
        if diagnostic.status == "available":
            if not isinstance(draw_error, Real) or not np.isfinite(draw_error):
                raise ValueError(
                    "available diagnostics require finite max draw conservation error"
                )
        elif not pd.isna(draw_error):
            raise ValueError(
                "partial or unavailable diagnostics require missing max draw "
                "conservation error"
            )
    available_group_keys = {
        key for key, row in diagnostic_lookup.items() if row.status == "available"
    }
    unavailable_group_keys = set(diagnostic_lookup).difference(available_group_keys)
    if normalized_draws.empty:
        if available_group_keys:
            raise ValueError("available diagnostics require complete retained draws")
        return
    normalized_draws["horizon_months"] = _normalize_count_column(
        normalized_draws["horizon_months"], "horizon_months", positive=True
    )
    normalized_draws["draw"] = _normalize_count_column(
        normalized_draws["draw"], "draw", positive=False
    )
    for column in ("contribution", "target_return"):
        normalized_draws[column] = _normalize_numeric_column(
            normalized_draws[column], column, allow_missing=False
        )
    draw_dimensions = (*_INTERVAL_DIMENSIONS, "draw")
    if normalized_draws.duplicated(list(draw_dimensions)).any():
        raise ValueError("draw dimensions must be unique")
    interval_keys = set(
        normalized_intervals.loc[
            normalized_intervals.set_index(list(_GROUP_DIMENSIONS)).index.isin(
                available_group_keys
            ),
            list(_INTERVAL_DIMENSIONS),
        ].itertuples(index=False, name=None)
    )
    draw_keys = set(
        normalized_draws.loc[:, list(_INTERVAL_DIMENSIONS)]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if draw_keys != interval_keys:
        raise ValueError("draw component keys must align with interval keys")
    draw_group_keys = set(
        normalized_draws.loc[:, list(_GROUP_DIMENSIONS)]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if draw_group_keys != available_group_keys or draw_group_keys.intersection(
        unavailable_group_keys
    ):
        raise ValueError(
            "retained draws are allowed only for available diagnostic groups"
        )
    expected_draw_ids = set(range(draw_count))
    interval_lookup = {
        tuple(getattr(row, column) for column in _INTERVAL_DIMENSIONS): row
        for row in normalized_intervals.itertuples(index=False)
    }
    for key, component_draws in normalized_draws.groupby(
        list(_INTERVAL_DIMENSIONS), sort=False
    ):
        if set(component_draws["draw"]) != expected_draw_ids:
            raise ValueError("retained components require complete draw ids")
        normalized_key = key if isinstance(key, tuple) else (key,)
        interval = interval_lookup[normalized_key]
        expected_bounds = np.quantile(
            component_draws["contribution"].to_numpy(dtype="float64"),
            [0.10, 0.25, 0.75, 0.90],
            method="linear",
        )
        published_bounds = np.asarray(
            [
                interval.lower_80,
                interval.lower_50,
                interval.upper_50,
                interval.upper_80,
            ],
            dtype="float64",
        )
        if not np.allclose(
            published_bounds,
            expected_bounds,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("published interval bounds do not match retained draws")
    draw_group_columns = [*_GROUP_DIMENSIONS, "draw"]
    actual_max_by_group: dict[tuple[object, ...], float] = {}
    for key, draw_group in normalized_draws.groupby(draw_group_columns, sort=False):
        targets = draw_group["target_return"].drop_duplicates().tolist()
        if len(targets) != 1:
            raise ValueError("target_return must be constant within each draw")
        error = abs(float(draw_group["contribution"].sum()) - float(targets[0]))
        group_key = key[:-1] if isinstance(key, tuple) else (key,)
        actual_max_by_group[group_key] = max(
            actual_max_by_group.get(group_key, 0.0), error
        )
    for key in available_group_keys:
        diagnostic = diagnostic_lookup[key]
        actual_error = actual_max_by_group.get(key)
        if actual_error is None or not np.isclose(
            diagnostic.max_draw_conservation_error,
            actual_error,
            atol=tolerance,
            rtol=0.0,
        ):
            raise ValueError("diagnostic draw conservation error is inconsistent")
        if actual_error > tolerance:
            raise ValueError("draw conservation exceeds tolerance")


def _estimate_single_month_intervals(
    contribution_result: object,
    *,
    stage1_paths: object,
    stage1_covariance: object | None,
    stage2_components: object,
    stage2_covariance: object | None,
    cycle_uncertainty: pd.DataFrame | None,
    channel_uncertainty: pd.DataFrame | None,
    residual_history: pd.DataFrame | None = None,
    period_start: object | None = None,
    period_end: object | None = None,
    horizon_months: int = 1,
    return_basis: str = "absolute",
    config: UncertaintyConfig | None = None,
    _raw: bool = False,
) -> object:
    """Estimate conserved component intervals without double-counting sources.

    Cycle state is drawn once per date and cycle and reused across channels. Stage 1
    coefficients are drawn jointly once per channel, while Stage 2 coefficients are
    drawn jointly once per asset. Channel beta draws are reused by cycle, baseline,
    and channel-residual paths. Channel uncertainty is restricted to residual or
    unresolved channel components, and past-only bootstrap noise is restricted to
    its exact residual component. Validated direct residual evidence is never
    bootstrapped from the asset residual again.
    """

    normalized_config = config or UncertaintyConfig()
    if not isinstance(normalized_config, UncertaintyConfig):
        raise TypeError("config must be an UncertaintyConfig")
    normalized_horizon = _positive_integer(horizon_months, "horizon_months")
    if normalized_horizon != 1:
        raise ValueError("single-date attribution currently requires horizon_months=1")
    if not isinstance(return_basis, str) or return_basis not in _VALID_RETURN_BASES:
        raise ValueError("return_basis must be 'absolute' or 'excess'")
    components, contribution_paths = _normalize_contribution_result(
        contribution_result,
        normalized_config.conservation_tolerance,
    )
    stage1 = _normalize_stage1_paths(stage1_paths)
    stage2 = _normalize_stage2_components(stage2_components)
    stage1_cov = _normalize_covariance(
        stage1_covariance,
        attribute="covariance",
        name="stage1_covariance",
        required=(
            "date",
            "channel_id",
            "cycle_i",
            "cycle_j",
            "coefficient_covariance",
            "training_count",
            "status",
        ),
        dimensions=("date", "channel_id", "cycle_i", "cycle_j"),
        support_column="training_count",
    )
    stage2_cov = _normalize_covariance(
        stage2_covariance,
        attribute="covariance",
        name="stage2_covariance",
        required=(
            "date",
            "node_level",
            "node_id",
            "component_i_type",
            "component_i_id",
            "component_j_type",
            "component_j_id",
            "coefficient_covariance",
            "training_count",
            "effective_training_count",
            "status",
        ),
        dimensions=(
            "date",
            "node_level",
            "node_id",
            "component_i_type",
            "component_i_id",
            "component_j_type",
            "component_j_id",
        ),
        support_column="effective_training_count",
    )
    cycle_unc = _normalize_uncertainty(
        cycle_uncertainty,
        id_column="cycle_id",
        name="cycle_uncertainty",
    )
    channel_unc = _normalize_uncertainty(
        channel_uncertainty,
        id_column="channel_id",
        name="channel_uncertainty",
    )
    residuals = _normalize_residual_history(residual_history)

    if period_end is not None:
        normalized_period_end = _normalize_date(period_end, "period_end")
    else:
        normalized_period_end = None
    if period_start is not None:
        normalized_period_start = _normalize_date(period_start, "period_start")
    else:
        normalized_period_start = None
    if (
        normalized_period_start is not None
        and normalized_period_end is not None
        and normalized_period_start > normalized_period_end
    ):
        raise ValueError("period_start cannot be later than period_end")

    stage1_groups = {
        key: group.reset_index(drop=True)
        for key, group in stage1.groupby(["date", "channel_id"], sort=False)
    }
    stage1_cov_groups = {
        key: group.reset_index(drop=True)
        for key, group in stage1_cov.groupby(["date", "channel_id"], sort=False)
    }
    stage2_groups = {
        key: group.reset_index(drop=True)
        for key, group in stage2.groupby(["date", "asset_id"], sort=False)
    }
    stage2_cov_groups = {
        (key[0], key[2]): group.reset_index(drop=True)
        for key, group in stage2_cov.loc[stage2_cov["node_level"].eq("asset")].groupby(
            ["date", "node_level", "node_id"], sort=False
        )
    }
    cycle_unc_lookup = {
        (row.date, row.cycle_id): float(row.uncertainty)
        for row in cycle_unc.itertuples(index=False)
        if np.isfinite(row.uncertainty)
    }
    channel_unc_lookup = {
        (row.date, row.channel_id): float(row.uncertainty)
        for row in channel_unc.itertuples(index=False)
        if np.isfinite(row.uncertainty)
    }

    cycle_draw_cache: dict[tuple[pd.Timestamp, str], tuple[np.ndarray, bool, int]] = {}
    stage1_draw_cache: dict[
        tuple[pd.Timestamp, str], tuple[np.ndarray, dict[str, int], bool, int]
    ] = {}
    stage2_draw_cache: dict[
        tuple[pd.Timestamp, str],
        tuple[np.ndarray, dict[tuple[str, str], int], bool, int],
    ] = {}
    channel_noise_cache: dict[
        tuple[pd.Timestamp, str], tuple[np.ndarray, bool, int]
    ] = {}
    residual_noise_cache: dict[
        tuple[pd.Timestamp, str, str, str], tuple[np.ndarray, bool, int]
    ] = {}

    def cycle_draws(
        current_date: pd.Timestamp,
        cycle_id: str,
        current_value: float,
    ) -> tuple[np.ndarray, bool, int]:
        key = (current_date, cycle_id)
        cached = cycle_draw_cache.get(key)
        if cached is not None:
            return cached
        uncertainty = cycle_unc_lookup.get(key)
        valid = np.isfinite(current_value) and (
            not normalized_config.enable_cycle_state or uncertainty is not None
        )
        if not normalized_config.enable_cycle_state:
            values = np.full(
                normalized_config.draw_count, current_value, dtype="float64"
            )
        else:
            values = (
                current_value
                + _rng(
                    normalized_config.seed,
                    "cycle_state",
                    current_date.isoformat(),
                    cycle_id,
                ).normal(0.0, uncertainty, normalized_config.draw_count)
                if valid
                else np.full(
                    normalized_config.draw_count, current_value, dtype="float64"
                )
            )
        output = (values, valid, 0)
        cycle_draw_cache[key] = output
        return output

    def stage1_draws(
        current_date: pd.Timestamp,
        channel_id: str,
    ) -> tuple[np.ndarray, dict[str, int], bool, int]:
        key = (current_date, channel_id)
        cached = stage1_draw_cache.get(key)
        if cached is not None:
            return cached
        group = stage1_groups.get(key)
        positions = {cycle_id: position for position, cycle_id in enumerate(CYCLE_IDS)}
        valid_current = (
            group is not None
            and len(group) == len(CYCLE_IDS)
            and set(group["cycle_id"]) == set(CYCLE_IDS)
            and group["status"].eq("estimated").all()
        )
        if valid_current:
            ordered = group.set_index("cycle_id").loc[list(CYCLE_IDS)]
            means = ordered["coefficient_mean"].to_numpy(dtype="float64")
            supports = ordered["training_count"].drop_duplicates().tolist()
            valid_current = np.isfinite(means).all() and len(supports) == 1
            effective_samples = int(supports[0]) if len(supports) == 1 else 0
        else:
            means = np.zeros(len(CYCLE_IDS), dtype="float64")
            effective_samples = 0
        valid = bool(valid_current)
        if normalized_config.enable_stage1_covariance and valid:
            covariance_group = stage1_cov_groups.get(key)
            covariance_supports = (
                []
                if covariance_group is None
                else covariance_group["training_count"].drop_duplicates().tolist()
            )
            covariance = (
                None
                if covariance_group is None
                or not covariance_group["status"].eq("estimated").all()
                or len(covariance_supports) != 1
                else _long_covariance_matrix(
                    covariance_group,
                    CYCLE_IDS,
                    row_columns=("cycle_i",),
                    column_columns=("cycle_j",),
                )
            )
            valid = covariance is not None
            if len(covariance_supports) == 1:
                covariance_support = int(covariance_supports[0])
                if covariance_support != effective_samples:
                    raise ValueError(
                        "Stage1 paths and covariance training_count must be consistent"
                    )
            draws = (
                _normal_draws(
                    means,
                    covariance,
                    draw_count=normalized_config.draw_count,
                    generator=_rng(
                        normalized_config.seed,
                        "stage1_coefficients",
                        current_date.isoformat(),
                        channel_id,
                    ),
                )
                if valid and covariance is not None
                else np.tile(means, (normalized_config.draw_count, 1))
            )
        else:
            draws = np.tile(means, (normalized_config.draw_count, 1))
        output = (draws, positions, valid, effective_samples)
        stage1_draw_cache[key] = output
        return output

    def stage2_draws(
        current_date: pd.Timestamp,
        asset_id: str,
    ) -> tuple[np.ndarray, dict[tuple[str, str], int], bool, int]:
        key = (current_date, asset_id)
        cached = stage2_draw_cache.get(key)
        if cached is not None:
            return cached
        group = stage2_groups.get(key)
        if group is None:
            output = (
                np.empty((normalized_config.draw_count, 0), dtype="float64"),
                {},
                False,
                0,
            )
            stage2_draw_cache[key] = output
            return output
        parameter_rows = group.loc[group["component_type"].ne("residual")].copy()
        labels = tuple(
            (str(row.component_type), str(row.component_id))
            for row in parameter_rows.itertuples(index=False)
        )
        positions = {label: position for position, label in enumerate(labels)}
        means = parameter_rows["coefficient_mean"].to_numpy(dtype="float64")
        training_supports = parameter_rows["training_count"].drop_duplicates().tolist()
        supports = parameter_rows["effective_training_count"].drop_duplicates().tolist()
        statuses = set(parameter_rows["status"])
        valid = (
            len(labels) == len(set(labels))
            and np.isfinite(means).all()
            and bool(statuses)
            and statuses.issubset(_USABLE_STAGE2_STATUSES)
            and len(supports) == 1
            and len(training_supports) == 1
        )
        effective_samples = int(supports[0]) if len(supports) == 1 else 0
        training_samples = (
            int(training_supports[0]) if len(training_supports) == 1 else 0
        )
        if normalized_config.enable_stage2_covariance and valid:
            covariance_group = stage2_cov_groups.get(key)
            covariance_supports = (
                []
                if covariance_group is None
                else covariance_group["effective_training_count"]
                .drop_duplicates()
                .tolist()
            )
            covariance_training_supports = (
                []
                if covariance_group is None
                else covariance_group["training_count"].drop_duplicates().tolist()
            )
            covariance = (
                None
                if covariance_group is None
                or not set(covariance_group["status"]).issubset(_USABLE_STAGE2_STATUSES)
                or len(covariance_supports) != 1
                or len(covariance_training_supports) != 1
                else _long_covariance_matrix(
                    covariance_group,
                    labels,
                    row_columns=("component_i_type", "component_i_id"),
                    column_columns=("component_j_type", "component_j_id"),
                )
            )
            valid = covariance is not None
            if len(covariance_supports) == 1 and len(covariance_training_supports) == 1:
                covariance_effective = int(covariance_supports[0])
                covariance_training = int(covariance_training_supports[0])
                if (
                    covariance_effective != effective_samples
                    or covariance_training != training_samples
                ):
                    raise ValueError(
                        "Stage2 components and covariance training_count and "
                        "effective_training_count must be consistent"
                    )
            draws = (
                _normal_draws(
                    means,
                    covariance,
                    draw_count=normalized_config.draw_count,
                    generator=_rng(
                        normalized_config.seed,
                        "stage2_coefficients",
                        current_date.isoformat(),
                        asset_id,
                    ),
                )
                if valid and covariance is not None
                else np.tile(means, (normalized_config.draw_count, 1))
            )
        else:
            draws = np.tile(means, (normalized_config.draw_count, 1))
        output = (draws, positions, valid, effective_samples)
        stage2_draw_cache[key] = output
        return output

    def channel_noise(
        current_date: pd.Timestamp,
        channel_id: str,
    ) -> tuple[np.ndarray, bool, int]:
        key = (current_date, channel_id)
        cached = channel_noise_cache.get(key)
        if cached is not None:
            return cached
        if not normalized_config.enable_channel_uncertainty:
            output = (np.zeros(normalized_config.draw_count), True, 0)
        else:
            uncertainty = channel_unc_lookup.get(key)
            valid = uncertainty is not None
            values = (
                _rng(
                    normalized_config.seed,
                    "channel_uncertainty",
                    current_date.isoformat(),
                    channel_id,
                ).normal(0.0, uncertainty, normalized_config.draw_count)
                if valid
                else np.zeros(normalized_config.draw_count)
            )
            output = (values, valid, 0)
        channel_noise_cache[key] = output
        return output

    def residual_noise(
        current_date: pd.Timestamp,
        asset_id: str,
        component_type: str,
        component_id: str,
        cutoff: pd.Timestamp,
    ) -> tuple[np.ndarray, bool, int]:
        key = (current_date, asset_id, component_type, component_id)
        cached = residual_noise_cache.get(key)
        if cached is not None:
            return cached
        if not normalized_config.enable_residual_bootstrap:
            output = (
                np.zeros(normalized_config.draw_count),
                True,
                0,
            )
        else:
            eligible = residuals.loc[
                residuals["date"].lt(cutoff)
                & residuals["asset_id"].eq(asset_id)
                & residuals["component_type"].eq(component_type)
                & residuals["component_id"].eq(component_id)
            ].sort_values("date", kind="stable")
            effective_samples = len(eligible)
            valid = (
                effective_samples >= normalized_config.min_effective_samples
                and effective_samples >= normalized_config.block_length
            )
            values = (
                _bootstrap_noise(
                    eligible["value"].to_numpy(dtype="float64"),
                    horizon_months=normalized_horizon,
                    config=normalized_config,
                    generator=_rng(
                        normalized_config.seed,
                        "residual_bootstrap",
                        current_date.isoformat(),
                        asset_id,
                        component_type,
                        component_id,
                    ),
                )
                if valid
                else np.zeros(normalized_config.draw_count)
            )
            output = (values, valid, effective_samples)
        residual_noise_cache[key] = output
        return output

    def stage1_point_support(
        current_date: pd.Timestamp,
        channel_id: str,
    ) -> tuple[pd.DataFrame | None, bool, int]:
        group = stage1_groups.get((current_date, channel_id))
        if group is None:
            return None, False, 0
        supports = group["training_count"].drop_duplicates().tolist()
        valid = (
            len(group) == len(CYCLE_IDS)
            and set(group["cycle_id"]) == set(CYCLE_IDS)
            and group["status"].eq("estimated").all()
            and len(supports) == 1
        )
        return group, valid, int(supports[0]) if len(supports) == 1 else 0

    interval_records: list[dict[str, object]] = []
    diagnostic_records: list[dict[str, object]] = []
    draw_records: list[dict[str, object]] = []
    for (current_date, asset_id), component_group in components.groupby(
        ["date", "asset_id"], sort=False
    ):
        group_period_end = normalized_period_end or current_date
        group_period_start = normalized_period_start or current_date
        if group_period_start != current_date or group_period_end != current_date:
            raise ValueError(
                "single-date attribution requires period_start and period_end "
                "to equal the attribution date with horizon_months=1"
            )
        residual_cutoff = current_date
        asset_residual_rows = component_group.loc[
            component_group["component_type"].eq("asset_residual")
        ]
        if len(asset_residual_rows) != 1:
            raise ValueError(
                "each asset/date group requires exactly one asset_residual component"
            )
        asset_residual_component = asset_residual_rows.iloc[0]
        stage2_group = stage2_groups.get((current_date, asset_id))
        stage2_values = (
            {}
            if stage2_group is None
            else {
                (str(row.component_type), str(row.component_id)): row
                for row in stage2_group.itertuples(index=False)
            }
        )
        beta_draws, beta_positions, stage2_valid, stage2_support = stage2_draws(
            current_date, asset_id
        )
        asset_paths = contribution_paths.loc[
            contribution_paths["date"].eq(current_date)
            & contribution_paths["asset_id"].eq(asset_id)
        ]
        generated_components: dict[tuple[str, str], dict[str, object]] = {}
        for component in component_group.itertuples(index=False):
            component_type = str(component.component_type)
            component_id = str(component.component_id)
            if component_type == "asset_residual":
                continue
            point = float(component.contribution)
            status = str(component.status)
            draws = np.full(normalized_config.draw_count, point, dtype="float64")
            model_valid = True
            degraded = False
            supports: list[int] = []

            if component_type in {"cycle", "cycle_group"}:
                selected_paths = asset_paths.loc[
                    asset_paths["allocation_group_id"].eq(component_id)
                ]
                generated = np.zeros(normalized_config.draw_count, dtype="float64")
                model_valid = not selected_paths.empty and stage2_valid
                supports.append(stage2_support)
                for path in selected_paths.itertuples(index=False):
                    channel_id = str(path.channel_id)
                    cycle_id = str(path.cycle_id)
                    stage1_group = stage1_groups.get((current_date, channel_id))
                    if stage1_group is None:
                        available = False
                        continue
                    current_cycle = stage1_group.loc[
                        stage1_group["cycle_id"].eq(cycle_id), "cycle_innovation"
                    ]
                    cycle_values, cycle_valid, _ = cycle_draws(
                        current_date,
                        cycle_id,
                        float(current_cycle.iloc[0])
                        if len(current_cycle) == 1
                        else np.nan,
                    )
                    (
                        coefficient_values,
                        coefficient_positions,
                        coefficient_valid,
                        coefficient_support,
                    ) = stage1_draws(current_date, channel_id)
                    supports.append(coefficient_support)
                    beta_position = beta_positions.get(("channel", channel_id))
                    path_valid = (
                        cycle_valid
                        and coefficient_valid
                        and beta_position is not None
                        and str(path.stage1_status) == "estimated"
                        and str(path.stage2_status) in _USABLE_STAGE2_STATUSES
                    )
                    model_valid = model_valid and path_valid
                    if path_valid and beta_position is not None:
                        generated += (
                            cycle_values
                            * coefficient_values[:, coefficient_positions[cycle_id]]
                            * beta_draws[:, beta_position]
                        )
                if model_valid:
                    draws = generated
            elif component_type in {
                "asset_intercept",
                "benchmark",
                "interaction",
                "control",
                "event",
            }:
                label = (
                    ("intercept", "intercept")
                    if component_type == "asset_intercept"
                    else (component_type, component_id)
                )
                source_row = stage2_values.get(label)
                beta_position = beta_positions.get(label)
                supports.append(stage2_support)
                model_valid = (
                    stage2_valid
                    and source_row is not None
                    and beta_position is not None
                    and np.isfinite(source_row.component_value)
                )
                if model_valid and beta_position is not None and source_row is not None:
                    draws = (
                        float(source_row.component_value) * beta_draws[:, beta_position]
                    )
            elif component_type == "channel_baseline_path":
                stage1_group, stage1_valid, stage1_support = stage1_point_support(
                    current_date, component_id
                )
                beta_position = beta_positions.get(("channel", component_id))
                supports.extend((stage1_support, stage2_support))
                model_valid = (
                    stage2_valid and stage1_valid and beta_position is not None
                )
                if (
                    model_valid
                    and stage1_group is not None
                    and beta_position is not None
                ):
                    intercepts = stage1_group["intercept"].drop_duplicates().tolist()
                    model_valid = len(intercepts) == 1 and np.isfinite(intercepts[0])
                    if model_valid:
                        draws = float(intercepts[0]) * beta_draws[:, beta_position]
            elif component_type in {"channel_residual_path", "unresolved_channel"}:
                beta_position = beta_positions.get(("channel", component_id))
                channel_values, channel_valid, _ = channel_noise(
                    current_date, component_id
                )
                supports.append(stage2_support)
                model_valid = (
                    stage2_valid and beta_position is not None and channel_valid
                )
                residual_values = np.zeros(normalized_config.draw_count)
                residual_valid = True
                if normalized_config.enable_residual_bootstrap:
                    (
                        residual_values,
                        residual_valid,
                        residual_support,
                    ) = residual_noise(
                        current_date,
                        asset_id,
                        component_type,
                        component_id,
                        residual_cutoff,
                    )
                    supports.append(residual_support)
                    model_valid = model_valid and residual_valid
                if model_valid and beta_position is not None:
                    if component_type == "channel_residual_path":
                        (
                            stage1_group,
                            stage1_valid,
                            stage1_support,
                        ) = stage1_point_support(current_date, component_id)
                        supports.append(stage1_support)
                        residual_level = np.nan
                        if stage1_group is not None:
                            levels = (
                                stage1_group["channel_residual"]
                                .drop_duplicates()
                                .tolist()
                            )
                            if len(levels) == 1:
                                residual_level = float(levels[0])
                        model_valid = stage1_valid and np.isfinite(residual_level)
                        if model_valid:
                            draws = (residual_level + channel_values) * beta_draws[
                                :, beta_position
                            ] + residual_values
                    else:
                        source_row = stage2_values.get(("channel", component_id))
                        model_valid = source_row is not None and np.isfinite(
                            source_row.component_value
                        )
                        if model_valid and source_row is not None:
                            draws = (
                                float(source_row.component_value) + channel_values
                            ) * beta_draws[:, beta_position] + residual_values
                            degraded = status in _FAILED_STATUSES
            elif component_type == "unobserved_channel_residual":
                model_valid = False
            else:
                model_valid = False

            if status in _FAILED_STATUSES and component_type != "unresolved_channel":
                model_valid = False
            effective_samples = min(supports) if supports else 0
            available = (
                model_valid
                and effective_samples >= normalized_config.min_effective_samples
            )
            generated_components[(component_type, component_id)] = {
                "component": component,
                "draws": draws,
                "model_valid": model_valid,
                "available": available,
                "degraded": degraded,
                "supports": supports,
                "effective_samples": effective_samples,
            }

        point_sum = float(component_group["contribution"].sum())
        observed = float(component_group["observed_return"].iloc[0])
        target_noise = np.zeros(normalized_config.draw_count)
        target_valid = True
        target_supports: list[int] = []
        if normalized_config.enable_residual_bootstrap:
            target_noise, target_valid, target_support = residual_noise(
                current_date,
                asset_id,
                "asset_residual",
                str(asset_residual_component["component_id"]),
                residual_cutoff,
            )
            target_supports.append(target_support)
        target_draws = observed + target_noise
        non_residual_draws = np.add.reduce(
            [
                np.asarray(values["draws"], dtype="float64")
                for values in generated_components.values()
            ],
            axis=0,
        )
        balanced_residual_draws = target_draws - non_residual_draws
        balance_supports = [
            support
            for values in generated_components.values()
            if str(values["component"].component_type) != "unobserved_channel_residual"
            for support in values["supports"]
        ]
        balance_supports.extend(target_supports)
        if not balance_supports:
            balance_supports.append(stage2_support)
        balance_effective_samples = min(balance_supports)
        balance_dependencies_available = all(
            bool(values["available"])
            for values in generated_components.values()
            if str(values["component"].component_type) != "unobserved_channel_residual"
        )
        residual_status = str(asset_residual_component["status"])
        balance_model_valid = (
            target_valid
            and balance_dependencies_available
            and residual_status not in _FAILED_STATUSES
        )
        balance_available = (
            balance_model_valid
            and balance_effective_samples >= normalized_config.min_effective_samples
        )
        generated_components[
            (
                "asset_residual",
                str(asset_residual_component["component_id"]),
            )
        ] = {
            "component": asset_residual_component,
            "draws": balanced_residual_draws,
            "model_valid": balance_model_valid,
            "available": balance_available,
            "degraded": False,
            "supports": balance_supports,
            "effective_samples": balance_effective_samples,
        }

        final_draws: list[np.ndarray] = []
        component_available: list[bool] = []
        for component in component_group.itertuples(index=False):
            component_type = str(component.component_type)
            component_id = str(component.component_id)
            values = generated_components[(component_type, component_id)]
            draws = np.asarray(values["draws"], dtype="float64")
            available = bool(values["available"])
            degraded = bool(values["degraded"])
            effective_samples = int(values["effective_samples"])
            interval_status = (
                "degraded"
                if available and degraded
                else "available"
                if available
                else "unavailable"
            )
            if available:
                lower_80, lower_50, upper_50, upper_80 = np.quantile(
                    draws,
                    [0.10, 0.25, 0.75, 0.90],
                    method="linear",
                ).tolist()
                significance = _significance(lower_80, upper_80)
            else:
                lower_50 = upper_50 = lower_80 = upper_80 = np.nan
                significance = "unavailable"
            interval_records.append(
                {
                    "asset_id": asset_id,
                    "period_start": group_period_start,
                    "period_end": group_period_end,
                    "horizon_months": normalized_horizon,
                    "return_basis": return_basis,
                    "component_type": component_type,
                    "component_id": component_id,
                    "point_contribution": float(component.contribution),
                    "lower_50": lower_50,
                    "upper_50": upper_50,
                    "lower_80": lower_80,
                    "upper_80": upper_80,
                    "interval_status": interval_status,
                    "significance": significance,
                    "effective_samples": effective_samples,
                    "draw_count": normalized_config.draw_count,
                    "status": str(component.status),
                    "evidence_level": _evidence_level(
                        available=available,
                        degraded=degraded,
                        effective_samples=effective_samples,
                        minimum=normalized_config.min_effective_samples,
                    ),
                    "observed_return": float(component.observed_return),
                    "reconstructed_return": float(component.reconstructed_return),
                    "is_explained": bool(component.is_explained),
                    "is_residual": bool(component.is_residual),
                }
            )
            final_draws.append(draws)
            component_available.append(available)
            if available:
                draw_records.extend(
                    {
                        "asset_id": asset_id,
                        "period_start": group_period_start,
                        "period_end": group_period_end,
                        "horizon_months": normalized_horizon,
                        "return_basis": return_basis,
                        "draw": draw_position,
                        "component_type": component_type,
                        "component_id": component_id,
                        "contribution": float(draw_value),
                        "target_return": float(target_draws[draw_position]),
                    }
                    for draw_position, draw_value in enumerate(draws)
                )
        reconstructed_draws = np.column_stack(final_draws).sum(axis=1)
        available_count = int(sum(component_available))
        unavailable_count = len(component_available) - available_count
        diagnostic_status = (
            "available"
            if unavailable_count == 0
            else "unavailable"
            if available_count == 0
            else "partial"
        )
        diagnostic_records.append(
            {
                "asset_id": asset_id,
                "period_start": group_period_start,
                "period_end": group_period_end,
                "horizon_months": normalized_horizon,
                "return_basis": return_basis,
                "point_component_sum": point_sum,
                "observed_return": observed,
                "point_conservation_error": abs(point_sum - observed),
                "max_draw_conservation_error": float(
                    np.max(np.abs(reconstructed_draws - target_draws))
                ),
                "available_component_count": available_count,
                "unavailable_component_count": unavailable_count,
                "status": diagnostic_status,
            }
        )

    intervals = pd.DataFrame.from_records(
        interval_records, columns=ATTRIBUTION_INTERVAL_COLUMNS
    )
    diagnostics = pd.DataFrame.from_records(
        diagnostic_records, columns=ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS
    )
    draws = pd.DataFrame.from_records(draw_records, columns=ATTRIBUTION_DRAW_COLUMNS)
    if _raw:
        return intervals, diagnostics, draws
    return AttributionIntervalResult(
        intervals=intervals,
        diagnostics=diagnostics,
        draws=draws,
        draw_count=normalized_config.draw_count,
        seed=normalized_config.seed,
    )


def estimate_attribution_intervals(
    contribution_result: object,
    *,
    stage1_paths: object,
    stage1_covariance: object | None,
    stage2_components: object,
    stage2_covariance: object | None,
    cycle_uncertainty: pd.DataFrame | None,
    channel_uncertainty: pd.DataFrame | None,
    residual_history: pd.DataFrame | None = None,
    period_start: object | None = None,
    period_end: object | None = None,
    horizon_months: int = 1,
    return_basis: str = "absolute",
    config: UncertaintyConfig | None = None,
) -> AttributionIntervalResult:
    """Estimate monthly or wealth-linked contiguous-period attribution intervals."""

    normalized_config = config or UncertaintyConfig()
    if not isinstance(normalized_config, UncertaintyConfig):
        raise TypeError("config must be an UncertaintyConfig")
    normalized_horizon = _positive_integer(horizon_months, "horizon_months")
    if not isinstance(return_basis, str) or return_basis not in _VALID_RETURN_BASES:
        raise ValueError("return_basis must be 'absolute' or 'excess'")
    components, contribution_paths = _normalize_contribution_result(
        contribution_result,
        normalized_config.conservation_tolerance,
    )
    residuals = _normalize_residual_history(residual_history)
    normalized_start = (
        None if period_start is None else _normalize_date(period_start, "period_start")
    )
    normalized_end = (
        None if period_end is None else _normalize_date(period_end, "period_end")
    )
    stage1_covariance_source = (
        None
        if stage1_covariance is None
        else _source_frame(stage1_covariance, "covariance", "stage1_covariance")
    )
    stage2_source = _source_frame(stage2_components, "components", "stage2_components")
    stage2_covariance_source = (
        None
        if stage2_covariance is None
        else _source_frame(stage2_covariance, "covariance", "stage2_covariance")
    )
    interval_records: list[dict[str, object]] = []
    diagnostic_records: list[dict[str, object]] = []
    draw_records: list[dict[str, object]] = []
    monthly_config = replace(
        normalized_config,
        enable_residual_bootstrap=False,
        min_effective_samples=1,
    )

    for asset_id, asset_components in components.groupby("asset_id", sort=False):
        dates = tuple(sorted(asset_components["date"].drop_duplicates().tolist()))
        if len(dates) != normalized_horizon:
            raise ValueError(
                "horizon_months must equal the number of contiguous monthly dates"
            )
        expected_dates = tuple(
            pd.date_range(dates[0], periods=len(dates), freq="ME").tolist()
        )
        if dates != expected_dates:
            raise ValueError("attribution inputs require contiguous monthly dates")
        asset_period_start = dates[0] if normalized_start is None else normalized_start
        asset_period_end = dates[-1] if normalized_end is None else normalized_end
        if asset_period_start != dates[0] or asset_period_end != dates[-1]:
            raise ValueError(
                "period_start and period_end must match the first and last monthly dates"
            )
        component_groups = {
            current_date: group.reset_index(drop=True)
            for current_date, group in asset_components.groupby("date", sort=False)
        }
        skeletons = [
            set(
                group.loc[:, ["component_type", "component_id"]].itertuples(
                    index=False, name=None
                )
            )
            for group in component_groups.values()
        ]
        component_keys = sorted(
            set().union(*skeletons),
            key=lambda key: (_COMPONENT_ORDER[key[0]], key[1]),
        )
        asset_residual_keys = [
            key for key in component_keys if key[0] == "asset_residual"
        ]
        if len(asset_residual_keys) != 1:
            raise ValueError(
                "each asset period requires exactly one asset_residual component"
            )
        asset_residual_key = asset_residual_keys[0]
        observed_monthly = np.asarray(
            [
                float(component_groups[current_date]["observed_return"].iloc[0])
                for current_date in dates
            ],
            dtype="float64",
        )
        if bool((observed_monthly <= -1.0).any()):
            raise ValueError("monthly observed returns must be greater than -100%")

        residual_path_cache: dict[tuple[str, str], tuple[np.ndarray, bool, int]] = {}

        def residual_path(
            component_type: str,
            component_id: str,
        ) -> tuple[np.ndarray, bool, int]:
            key = (component_type, component_id)
            cached = residual_path_cache.get(key)
            if cached is not None:
                return cached
            if not normalized_config.enable_residual_bootstrap:
                output = (
                    np.zeros(
                        (normalized_config.draw_count, normalized_horizon),
                        dtype="float64",
                    ),
                    True,
                    0,
                )
            else:
                eligible = residuals.loc[
                    residuals["date"].lt(asset_period_start)
                    & residuals["asset_id"].eq(asset_id)
                    & residuals["component_type"].eq(component_type)
                    & residuals["component_id"].eq(component_id)
                ].sort_values("date", kind="stable")
                effective_samples = len(eligible)
                required_history = max(
                    normalized_config.min_effective_samples,
                    normalized_config.block_length,
                )
                span = normalized_config.block_length
                eligible_dates = eligible["date"].tolist()
                valid_starts = np.asarray(
                    [
                        start
                        for start in range(max(0, len(eligible_dates) - span + 1))
                        if eligible_dates[start : start + span]
                        == pd.date_range(
                            eligible_dates[start],
                            periods=span,
                            freq="ME",
                        ).tolist()
                    ],
                    dtype="int64",
                )
                valid = effective_samples >= required_history and len(valid_starts) > 0
                values = (
                    _bootstrap_noise_path(
                        eligible["value"].to_numpy(dtype="float64"),
                        horizon_months=normalized_horizon,
                        config=normalized_config,
                        generator=_rng(
                            normalized_config.seed,
                            "period_residual_block",
                            asset_id,
                            component_type,
                            component_id,
                            asset_period_start.isoformat(),
                            asset_period_end.isoformat(),
                        ),
                        valid_starts=valid_starts,
                    )
                    if valid
                    else np.zeros(
                        (normalized_config.draw_count, normalized_horizon),
                        dtype="float64",
                    )
                )
                output = (values, valid, effective_samples)
            residual_path_cache[key] = output
            return output

        target_noise, target_valid, target_support = residual_path(
            *asset_residual_key,
        )
        monthly_targets = observed_monthly[None, :] + target_noise
        if target_valid and bool((monthly_targets <= -1.0).any()):
            raise ValueError("monthly target draws must be greater than -100%")
        monthly_points: dict[tuple[str, str], np.ndarray] = {
            key: np.zeros(normalized_horizon, dtype="float64") for key in component_keys
        }
        monthly_draws: dict[tuple[str, str], np.ndarray] = {
            key: np.zeros(
                (normalized_config.draw_count, normalized_horizon),
                dtype="float64",
            )
            for key in component_keys
        }
        monthly_available: dict[tuple[str, str], list[bool]] = {
            key: [] for key in component_keys
        }
        monthly_degraded: dict[tuple[str, str], list[bool]] = {
            key: [] for key in component_keys
        }
        component_supports: dict[tuple[str, str], list[int]] = {
            key: [] for key in component_keys
        }
        component_metadata: dict[tuple[str, str], list[pd.Series]] = {
            key: [] for key in component_keys
        }

        for month_position, current_date in enumerate(dates):
            monthly_components = component_groups[current_date]
            monthly_paths = contribution_paths.loc[
                contribution_paths["date"].eq(current_date)
                & contribution_paths["asset_id"].eq(asset_id)
            ]
            monthly_contribution = _ContributionFrames(
                components=monthly_components,
                paths=monthly_paths,
            )
            stage1_covariance_month = (
                None
                if stage1_covariance_source is None
                else stage1_covariance_source.loc[
                    pd.to_datetime(stage1_covariance_source["date"])
                    .dt.normalize()
                    .eq(current_date)
                ]
            )
            stage2_month = stage2_source.loc[
                pd.to_datetime(stage2_source["date"]).dt.normalize().eq(current_date)
                & stage2_source["asset_id"].eq(asset_id)
            ]
            stage2_covariance_month = (
                None
                if stage2_covariance_source is None
                else stage2_covariance_source.loc[
                    pd.to_datetime(stage2_covariance_source["date"])
                    .dt.normalize()
                    .eq(current_date)
                    & stage2_covariance_source["node_id"].eq(asset_id)
                ]
            )
            cycle_uncertainty_month = (
                None
                if cycle_uncertainty is None
                else cycle_uncertainty.loc[
                    pd.to_datetime(cycle_uncertainty["date"])
                    .dt.normalize()
                    .eq(current_date)
                ]
            )
            channel_uncertainty_month = (
                None
                if channel_uncertainty is None
                else channel_uncertainty.loc[
                    pd.to_datetime(channel_uncertainty["date"])
                    .dt.normalize()
                    .eq(current_date)
                ]
            )
            monthly_interval_frame, _, monthly_draw_frame = (
                _estimate_single_month_intervals(
                    monthly_contribution,
                    stage1_paths=stage1_paths,
                    stage1_covariance=stage1_covariance_month,
                    stage2_components=stage2_month,
                    stage2_covariance=stage2_covariance_month,
                    cycle_uncertainty=cycle_uncertainty_month,
                    channel_uncertainty=channel_uncertainty_month,
                    residual_history=None,
                    period_start=current_date,
                    period_end=current_date,
                    horizon_months=1,
                    return_basis=return_basis,
                    config=monthly_config,
                    _raw=True,
                )
            )
            interval_lookup = {
                (str(row.component_type), str(row.component_id)): row
                for row in monthly_interval_frame.itertuples(index=False)
            }
            draw_pivot = monthly_draw_frame.pivot(
                index="draw",
                columns=["component_type", "component_id"],
                values="contribution",
            )
            component_lookup = {
                (str(row.component_type), str(row.component_id)): pd.Series(
                    row._asdict()
                )
                for row in monthly_components.itertuples(index=False)
            }
            for key in component_keys:
                source = component_lookup.get(key)
                interval = interval_lookup.get(key)
                if source is not None:
                    monthly_points[key][month_position] = float(source["contribution"])
                    component_metadata[key].append(source)
                draw_available = (
                    source is not None
                    and interval is not None
                    and interval.interval_status != "unavailable"
                    and key in draw_pivot
                )
                if draw_available and interval is not None:
                    monthly_draws[key][:, month_position] = draw_pivot[key].to_numpy(
                        dtype="float64"
                    )
                    degraded = interval.interval_status == "degraded"
                    component_supports[key].append(int(interval.effective_samples))
                else:
                    degraded = False
                    if interval is not None:
                        component_supports[key].append(int(interval.effective_samples))
                monthly_available[key].append(bool(draw_available))
                monthly_degraded[key].append(bool(degraded))

        for key in component_keys:
            component_type, component_id = key
            if (
                normalized_config.enable_residual_bootstrap
                and component_type
                not in {"asset_residual", "unobserved_channel_residual"}
                and any(bool(row["is_residual"]) for row in component_metadata[key])
            ):
                noise, valid, support = residual_path(component_type, component_id)
                monthly_draws[key] += noise
                monthly_available[key] = [
                    value and valid for value in monthly_available[key]
                ]
                component_supports[key].append(support)

        non_asset_keys = [key for key in component_keys if key[0] != "asset_residual"]
        complete_non_asset_distribution = target_valid and all(
            all(monthly_available[key]) for key in non_asset_keys
        )
        if complete_non_asset_distribution:
            monthly_draws[asset_residual_key] = monthly_targets - np.add.reduce(
                [monthly_draws[key] for key in non_asset_keys],
                axis=0,
            )
        else:
            monthly_draws[asset_residual_key][:] = np.nan
        monthly_available[asset_residual_key] = [
            complete_non_asset_distribution
        ] * normalized_horizon
        if normalized_config.enable_residual_bootstrap:
            component_supports[asset_residual_key].append(target_support)
        component_supports[asset_residual_key].extend(
            support
            for key in non_asset_keys
            if key[0] != "unobserved_channel_residual"
            for support in component_supports[key]
        )

        point_start_wealth = np.ones(normalized_horizon, dtype="float64")
        if normalized_horizon > 1:
            point_start_wealth[1:] = np.cumprod(1.0 + observed_monthly[:-1])
        period_observed = float(np.prod(1.0 + observed_monthly) - 1.0)
        draw_start_wealth = np.ones_like(monthly_targets)
        if normalized_horizon > 1:
            draw_start_wealth[:, 1:] = np.cumprod(
                1.0 + monthly_targets[:, :-1],
                axis=1,
            )
        period_target_draws = np.prod(1.0 + monthly_targets, axis=1) - 1.0
        period_component_draws: dict[tuple[str, str], np.ndarray] = {}
        period_component_points: dict[tuple[str, str], float] = {}
        period_component_available: dict[tuple[str, str], bool] = {}

        for key in component_keys:
            period_component_points[key] = float(
                np.sum(point_start_wealth * monthly_points[key])
            )
            period_component_draws[key] = np.sum(
                draw_start_wealth * monthly_draws[key],
                axis=1,
            )
            metadata = component_metadata[key]
            metadata_consistent = bool(metadata) and all(
                row["status"] == metadata[0]["status"]
                and bool(row["is_explained"]) == bool(metadata[0]["is_explained"])
                and bool(row["is_residual"]) == bool(metadata[0]["is_residual"])
                for row in metadata
            )
            wealth_support_available = target_valid or normalized_horizon == 1
            period_component_available[key] = (
                len(metadata) == normalized_horizon
                and metadata_consistent
                and all(monthly_available[key])
                and wealth_support_available
            )
            if normalized_horizon > 1 and normalized_config.enable_residual_bootstrap:
                component_supports[key].append(target_support)

        period_effective_samples = {
            key: min(component_supports[key]) if component_supports[key] else 0
            for key in component_keys
        }
        final_component_available = {
            key: (
                period_component_available[key]
                and period_effective_samples[key]
                >= normalized_config.min_effective_samples
            )
            for key in component_keys
        }
        period_distribution_available = all(final_component_available.values())
        if period_distribution_available:
            period_draw_sum = np.add.reduce(
                [period_component_draws[key] for key in component_keys],
                axis=0,
            )
            max_draw_error = float(
                np.max(np.abs(period_draw_sum - period_target_draws))
            )
        else:
            max_draw_error = np.nan

        for key in component_keys:
            component_type, component_id = key
            metadata = component_metadata[key]
            source = metadata[0]
            effective_samples = period_effective_samples[key]
            available = final_component_available[key]
            degraded = available and any(monthly_degraded[key])
            if available:
                lower_80, lower_50, upper_50, upper_80 = np.quantile(
                    period_component_draws[key],
                    [0.10, 0.25, 0.75, 0.90],
                    method="linear",
                ).tolist()
                significance = _significance(lower_80, upper_80)
                interval_status = "degraded" if degraded else "available"
            else:
                lower_50 = upper_50 = lower_80 = upper_80 = np.nan
                significance = "unavailable"
                interval_status = "unavailable"
            interval_records.append(
                {
                    "asset_id": asset_id,
                    "period_start": asset_period_start,
                    "period_end": asset_period_end,
                    "horizon_months": normalized_horizon,
                    "return_basis": return_basis,
                    "component_type": component_type,
                    "component_id": component_id,
                    "point_contribution": period_component_points[key],
                    "lower_50": lower_50,
                    "upper_50": upper_50,
                    "lower_80": lower_80,
                    "upper_80": upper_80,
                    "interval_status": interval_status,
                    "significance": significance,
                    "effective_samples": effective_samples,
                    "draw_count": normalized_config.draw_count,
                    "status": str(source["status"]),
                    "evidence_level": _evidence_level(
                        available=available,
                        degraded=degraded,
                        effective_samples=effective_samples,
                        minimum=normalized_config.min_effective_samples,
                    ),
                    "observed_return": period_observed,
                    "reconstructed_return": period_observed,
                    "is_explained": bool(source["is_explained"]),
                    "is_residual": bool(source["is_residual"]),
                }
            )

        available_count = int(sum(final_component_available.values()))
        unavailable_count = len(component_keys) - available_count
        diagnostic_status = (
            "available"
            if unavailable_count == 0
            else "unavailable"
            if available_count == 0
            else "partial"
        )
        point_component_sum = float(sum(period_component_points.values()))
        diagnostic_records.append(
            {
                "asset_id": asset_id,
                "period_start": asset_period_start,
                "period_end": asset_period_end,
                "horizon_months": normalized_horizon,
                "return_basis": return_basis,
                "point_component_sum": point_component_sum,
                "observed_return": period_observed,
                "point_conservation_error": abs(point_component_sum - period_observed),
                "max_draw_conservation_error": (
                    max_draw_error if diagnostic_status == "available" else np.nan
                ),
                "available_component_count": available_count,
                "unavailable_component_count": unavailable_count,
                "status": diagnostic_status,
            }
        )
        if diagnostic_status == "available":
            draw_records.extend(
                {
                    "asset_id": asset_id,
                    "period_start": asset_period_start,
                    "period_end": asset_period_end,
                    "horizon_months": normalized_horizon,
                    "return_basis": return_basis,
                    "draw": draw_position,
                    "component_type": component_type,
                    "component_id": component_id,
                    "contribution": float(period_component_draws[key][draw_position]),
                    "target_return": float(period_target_draws[draw_position]),
                }
                for key in component_keys
                for component_type, component_id in (key,)
                for draw_position in range(normalized_config.draw_count)
            )

    intervals = pd.DataFrame.from_records(
        interval_records,
        columns=ATTRIBUTION_INTERVAL_COLUMNS,
    )
    diagnostics = pd.DataFrame.from_records(
        diagnostic_records,
        columns=ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
    )
    draws = pd.DataFrame.from_records(draw_records, columns=ATTRIBUTION_DRAW_COLUMNS)
    return AttributionIntervalResult(
        intervals=intervals,
        diagnostics=diagnostics,
        draws=draws,
        draw_count=normalized_config.draw_count,
        seed=normalized_config.seed,
    )


__all__ = [
    "ATTRIBUTION_DRAW_COLUMNS",
    "ATTRIBUTION_INTERVAL_COLUMNS",
    "ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS",
    "CHANNEL_UNCERTAINTY_COLUMNS",
    "CYCLE_UNCERTAINTY_COLUMNS",
    "AttributionIntervalResult",
    "UncertaintyConfig",
    "estimate_attribution_intervals",
]
