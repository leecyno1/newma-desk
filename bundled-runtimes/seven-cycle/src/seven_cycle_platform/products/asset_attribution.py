"""Stable asset attribution interval and conservation products."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from numbers import Integral, Real
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.attribution.uncertainty import (
    ATTRIBUTION_INTERVAL_COLUMNS,
    ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
    AttributionIntervalResult,
)
from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ASSET_ATTRIBUTION_SCHEMA,
)
from seven_cycle_platform.storage.run_context import RunContext


ASSET_ATTRIBUTION_FILENAME = "asset_attribution.parquet"
ASSET_ATTRIBUTION_CONSERVATION_FILENAME = "asset_attribution_conservation.parquet"
ASSET_ATTRIBUTION_COLUMNS = tuple(ASSET_ATTRIBUTION_SCHEMA.names)
ASSET_ATTRIBUTION_CONSERVATION_COLUMNS = tuple(
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA.names
)

_PROVENANCE_COLUMNS = (
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
)
_ATTRIBUTION_DIMENSIONS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
    "component_type",
    "component_id",
)
_GROUP_DIMENSIONS = (
    "asset_id",
    "period_start",
    "period_end",
    "horizon_months",
    "return_basis",
)
_BOUND_COLUMNS = ("lower_50", "upper_50", "lower_80", "upper_80")
_VALID_RETURN_BASES = frozenset({"absolute", "excess"})
_VALID_INTERVAL_STATUSES = frozenset({"available", "degraded", "unavailable"})
_VALID_SIGNIFICANCE = frozenset(
    {"positive", "negative", "not_significant", "unavailable"}
)
_VALID_EVIDENCE = frozenset({"high", "medium", "low"})
_VALID_DIAGNOSTIC_STATUSES = frozenset({"available", "partial", "unavailable"})
_FAILED_ATTRIBUTION_STATUSES = frozenset(
    {"insufficient_history", "not_identifiable", "unavailable"}
)
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
_BASIS_ORDER = {"absolute": 0, "excess": 1}
_CONSERVATION_TOLERANCE = 1e-10
_RESULT_FIELDS = frozenset({"attribution", "conservation"})
_VALIDATED_PRODUCT_TOKEN = object()


def _copy_frame(values: pd.DataFrame) -> pd.DataFrame:
    return values.copy(deep=True)


@dataclass(frozen=True)
class AssetAttributionProduct:
    """Detached synchronized attribution and conservation product frames."""

    attribution: pd.DataFrame
    conservation: pd.DataFrame
    _validation_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        attribution = object.__getattribute__(self, "attribution")
        conservation = object.__getattribute__(self, "conservation")
        validation_token = object.__getattribute__(self, "_validation_token")
        if validation_token is not _VALIDATED_PRODUCT_TOKEN:
            raise TypeError(
                "AssetAttributionProduct must be created by build_asset_attribution"
            )
        if not isinstance(attribution, pd.DataFrame):
            raise TypeError("attribution must be a pandas DataFrame")
        if not isinstance(conservation, pd.DataFrame):
            raise TypeError("conservation must be a pandas DataFrame")
        if tuple(attribution.columns) != ASSET_ATTRIBUTION_COLUMNS:
            raise ValueError("attribution columns do not match the stable schema")
        if tuple(conservation.columns) != ASSET_ATTRIBUTION_CONSERVATION_COLUMNS:
            raise ValueError("conservation columns do not match the stable schema")
        object.__setattr__(self, "attribution", _copy_frame(attribution))
        object.__setattr__(self, "conservation", _copy_frame(conservation))

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name in _RESULT_FIELDS and isinstance(value, pd.DataFrame):
            return _copy_frame(value)
        return value

    def __iter__(self) -> Iterator[pd.DataFrame]:
        yield self.attribution
        yield self.conservation


def _validate_context(context: object) -> RunContext:
    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    return context


def _normalize_date(value: object, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must contain dates")
    if not isinstance(value, (date, datetime, np.datetime64, pd.Timestamp, str)):
        raise TypeError(f"{name} must contain dates")
    try:
        normalized = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must contain valid dates") from error
    if pd.isna(normalized):
        raise ValueError(f"{name} cannot contain missing dates")
    if normalized.tzinfo is not None:
        normalized = normalized.tz_convert(timezone.utc).tz_localize(None)
    return normalized.normalize()


def _normalize_dates(values: pd.Series, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_date(value, name) for value in values.tolist()],
        index=values.index,
        dtype="datetime64[ns]",
    )


def _normalize_identifier(values: pd.Series, name: str) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if not isinstance(value, str) or not value:
            raise TypeError(f"{name} values must be non-empty strings")
        normalized.append(value)
    return pd.Series(normalized, index=values.index, dtype="object")


def _normalize_real(
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
            raise TypeError(f"{name} values must be real numbers")
        numeric = float(value)
        if not np.isfinite(numeric):
            raise ValueError(f"{name} values must be finite")
        if nonnegative and numeric < 0.0:
            raise ValueError(f"{name} values must be nonnegative")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="float64")


def _normalize_count(
    values: pd.Series,
    name: str,
    *,
    positive: bool,
) -> pd.Series:
    normalized: list[int] = []
    for value in values.tolist():
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (Integral, np.integer)
        ):
            qualifier = "positive" if positive else "nonnegative"
            raise TypeError(f"{name} values must be {qualifier} integers")
        numeric = int(value)
        if numeric < (1 if positive else 0):
            qualifier = "positive" if positive else "nonnegative"
            raise ValueError(f"{name} values must be {qualifier} integers")
        normalized.append(numeric)
    return pd.Series(normalized, index=values.index, dtype="int64")


def _reject_caller_provenance(values: pd.DataFrame, name: str) -> None:
    prohibited = sorted(set(_PROVENANCE_COLUMNS).intersection(values.columns))
    if prohibited:
        raise ValueError(
            "product provenance must come only from RunContext; remove "
            + ", ".join(prohibited)
            + f" from {name}"
        )


def _required_source_columns(
    values: object,
    *,
    columns: tuple[str, ...],
    name: str,
) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if values.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique")
    _reject_caller_provenance(values, name)
    missing = [column for column in columns if column not in values.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(missing)}")
    unexpected = sorted(set(values.columns).difference(columns))
    if unexpected:
        raise ValueError(f"unexpected {name} columns: {', '.join(unexpected)}")
    if values.empty:
        raise ValueError(f"{name} must contain at least one row")
    return values.loc[:, list(columns)].copy(deep=True)


def _normalize_intervals(values: object) -> pd.DataFrame:
    frame = _required_source_columns(
        values,
        columns=ATTRIBUTION_INTERVAL_COLUMNS,
        name="intervals",
    )
    for column in ("period_start", "period_end"):
        frame[column] = _normalize_dates(frame[column], column)
    for column in (
        "asset_id",
        "return_basis",
        "component_type",
        "component_id",
        "significance",
        "interval_status",
        "status",
        "evidence_level",
    ):
        frame[column] = _normalize_identifier(frame[column], column)
    frame["horizon_months"] = _normalize_count(
        frame["horizon_months"], "horizon_months", positive=True
    )
    frame["effective_samples"] = _normalize_count(
        frame["effective_samples"], "effective_samples", positive=False
    )
    frame["draw_count"] = _normalize_count(
        frame["draw_count"], "draw_count", positive=True
    )
    if frame["draw_count"].nunique() != 1:
        raise ValueError("draw_count must be constant across the product")
    for column in (
        "point_contribution",
        "observed_return",
        "reconstructed_return",
    ):
        frame[column] = _normalize_real(frame[column], column, allow_missing=False)
    for column in _BOUND_COLUMNS:
        frame[column] = _normalize_real(frame[column], column, allow_missing=True)
    for column in ("is_explained", "is_residual"):
        if any(
            not isinstance(value, (bool, np.bool_)) for value in frame[column].tolist()
        ):
            raise TypeError(f"{column} values must be boolean")
        frame[column] = frame[column].astype("bool")
    if not set(frame["return_basis"]).issubset(_VALID_RETURN_BASES):
        raise ValueError("return_basis must contain only absolute or excess")
    if not set(frame["interval_status"]).issubset(_VALID_INTERVAL_STATUSES):
        raise ValueError("interval_status contains an unknown value")
    if not set(frame["significance"]).issubset(_VALID_SIGNIFICANCE):
        raise ValueError("significance contains an unknown value")
    if not set(frame["evidence_level"]).issubset(_VALID_EVIDENCE):
        raise ValueError("evidence_level contains an unknown value")
    if frame.duplicated(list(_ATTRIBUTION_DIMENSIONS)).any():
        raise ValueError("asset attribution dimensions must be unique")
    if bool((frame["period_start"] > frame["period_end"]).any()):
        raise ValueError("period_start cannot be later than period_end")
    for row in frame.itertuples(index=False):
        bounds = np.asarray(
            [row.lower_50, row.upper_50, row.lower_80, row.upper_80],
            dtype="float64",
        )
        if row.interval_status == "unavailable":
            if not np.isnan(bounds).all():
                raise ValueError(
                    "unavailable intervals require all four bounds to be NaN"
                )
            if row.significance != "unavailable":
                raise ValueError(
                    "unavailable interval significance must be unavailable"
                )
            if row.evidence_level != "low":
                raise ValueError("unavailable intervals require low evidence")
            continue
        if not np.isfinite(bounds).all():
            raise ValueError("available intervals require finite bounds")
        if not row.lower_80 <= row.lower_50 <= row.upper_50 <= row.upper_80:
            raise ValueError("interval bounds must be nested 50% within 80%")
        expected_significance = (
            "positive"
            if row.lower_80 > 0.0
            else "negative"
            if row.upper_80 < 0.0
            else "not_significant"
        )
        if row.significance != expected_significance:
            raise ValueError("significance must match the 80% interval")
        if row.interval_status == "degraded" and row.evidence_level != "low":
            raise ValueError("degraded intervals require low evidence")
        if (
            row.status in _FAILED_ATTRIBUTION_STATUSES
            and row.interval_status == "available"
        ):
            raise ValueError(
                "failed attribution status cannot publish an available interval"
            )
    for _, group in frame.groupby(list(_GROUP_DIMENSIONS), sort=False):
        observed = float(group["observed_return"].iloc[0])
        reconstructed = float(group["reconstructed_return"].iloc[0])
        if not np.allclose(
            group["observed_return"], observed, atol=_CONSERVATION_TOLERANCE, rtol=0.0
        ):
            raise ValueError(
                "observed_return must be constant within product dimensions"
            )
        if not np.allclose(
            group["reconstructed_return"],
            reconstructed,
            atol=_CONSERVATION_TOLERANCE,
            rtol=0.0,
        ):
            raise ValueError(
                "reconstructed_return must be constant within product dimensions"
            )
        point_sum = float(group["point_contribution"].sum())
        if not np.isclose(point_sum, observed, atol=_CONSERVATION_TOLERANCE, rtol=0.0):
            raise ValueError("point conservation does not match observed_return")
        if not np.isclose(
            reconstructed, observed, atol=_CONSERVATION_TOLERANCE, rtol=0.0
        ):
            raise ValueError(
                "point reconstructed_return does not match observed_return"
            )
    return frame


def _normalize_diagnostics(values: object) -> pd.DataFrame:
    frame = _required_source_columns(
        values,
        columns=ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS,
        name="diagnostics",
    )
    for column in ("period_start", "period_end"):
        frame[column] = _normalize_dates(frame[column], column)
    for column in ("asset_id", "return_basis", "status"):
        frame[column] = _normalize_identifier(frame[column], column)
    frame["horizon_months"] = _normalize_count(
        frame["horizon_months"], "horizon_months", positive=True
    )
    for column in ("available_component_count", "unavailable_component_count"):
        frame[column] = _normalize_count(frame[column], column, positive=False)
    for column in (
        "point_component_sum",
        "observed_return",
        "point_conservation_error",
    ):
        frame[column] = _normalize_real(
            frame[column],
            column,
            allow_missing=False,
            nonnegative=column.endswith("error"),
        )
    frame["max_draw_conservation_error"] = _normalize_real(
        frame["max_draw_conservation_error"],
        "max_draw_conservation_error",
        allow_missing=True,
        nonnegative=True,
    )
    if not set(frame["return_basis"]).issubset(_VALID_RETURN_BASES):
        raise ValueError("return_basis must contain only absolute or excess")
    if not set(frame["status"]).issubset(_VALID_DIAGNOSTIC_STATUSES):
        raise ValueError("diagnostic status contains an unknown value")
    if frame.duplicated(list(_GROUP_DIMENSIONS)).any():
        raise ValueError("conservation diagnostic dimensions must be unique")
    if bool((frame["period_start"] > frame["period_end"]).any()):
        raise ValueError("period_start cannot be later than period_end")
    if bool((frame["point_conservation_error"] > _CONSERVATION_TOLERANCE).any()):
        raise ValueError("conservation diagnostics exceed tolerance")
    for row in frame.itertuples(index=False):
        if row.status == "available":
            if not np.isfinite(row.max_draw_conservation_error):
                raise ValueError(
                    "available diagnostics require finite max draw conservation error"
                )
            if row.max_draw_conservation_error > _CONSERVATION_TOLERANCE:
                raise ValueError("conservation diagnostics exceed tolerance")
        elif not pd.isna(row.max_draw_conservation_error):
            raise ValueError(
                "partial or unavailable diagnostics require missing max draw "
                "conservation error"
            )
    return frame


def _validate_cross_product(
    intervals: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    diagnostic_lookup = {
        tuple(getattr(row, column) for column in _GROUP_DIMENSIONS): row
        for row in diagnostics.itertuples(index=False)
    }
    interval_keys = {
        tuple(key if isinstance(key, tuple) else (key,))
        for key in intervals.groupby(list(_GROUP_DIMENSIONS), sort=False).groups
    }
    if set(diagnostic_lookup) != interval_keys:
        raise ValueError("conservation diagnostics must align with attribution groups")
    for key, group in intervals.groupby(list(_GROUP_DIMENSIONS), sort=False):
        normalized_key = key if isinstance(key, tuple) else (key,)
        diagnostic = diagnostic_lookup[normalized_key]
        point_sum = float(group["point_contribution"].sum())
        observed = float(group["observed_return"].iloc[0])
        available_count = int(group["interval_status"].ne("unavailable").sum())
        unavailable_count = len(group) - available_count
        expected_status = (
            "available"
            if unavailable_count == 0
            else "unavailable"
            if available_count == 0
            else "partial"
        )
        if not np.isclose(
            diagnostic.point_component_sum,
            point_sum,
            atol=_CONSERVATION_TOLERANCE,
            rtol=0.0,
        ):
            raise ValueError(
                "diagnostic point_component_sum does not match attribution"
            )
        if not np.isclose(
            diagnostic.observed_return,
            observed,
            atol=_CONSERVATION_TOLERANCE,
            rtol=0.0,
        ):
            raise ValueError("diagnostic observed_return does not match attribution")
        expected_error = abs(point_sum - observed)
        if not np.isclose(
            diagnostic.point_conservation_error,
            expected_error,
            atol=_CONSERVATION_TOLERANCE,
            rtol=0.0,
        ):
            raise ValueError("diagnostic point conservation error is inconsistent")
        if diagnostic.available_component_count != available_count:
            raise ValueError("diagnostic available component count is inconsistent")
        if diagnostic.unavailable_component_count != unavailable_count:
            raise ValueError("diagnostic unavailable component count is inconsistent")
        if diagnostic.status != expected_status:
            raise ValueError(
                "diagnostic status is inconsistent with component availability"
            )
        if expected_status == "available":
            if not np.isfinite(diagnostic.max_draw_conservation_error):
                raise ValueError(
                    "available diagnostics require finite max draw conservation error"
                )
        elif not pd.isna(diagnostic.max_draw_conservation_error):
            raise ValueError(
                "partial or unavailable diagnostics require missing max draw "
                "conservation error"
            )


def _sort_attribution(values: pd.DataFrame) -> pd.DataFrame:
    component_order = values["component_type"].map(_COMPONENT_ORDER)
    if component_order.isna().any():
        unknown = sorted(set(values.loc[component_order.isna(), "component_type"]))
        raise ValueError("unknown component_type: " + ", ".join(unknown))
    basis_order = values["return_basis"].map(_BASIS_ORDER)
    return (
        values.assign(_component_order=component_order, _basis_order=basis_order)
        .sort_values(
            [
                "asset_id",
                "period_start",
                "period_end",
                "horizon_months",
                "_basis_order",
                "_component_order",
                "component_id",
            ],
            kind="stable",
        )
        .drop(columns=["_component_order", "_basis_order"])
        .reset_index(drop=True)
    )


def _sort_conservation(values: pd.DataFrame) -> pd.DataFrame:
    return (
        values.assign(_basis_order=values["return_basis"].map(_BASIS_ORDER))
        .sort_values(
            [
                "asset_id",
                "period_start",
                "period_end",
                "horizon_months",
                "_basis_order",
            ],
            kind="stable",
        )
        .drop(columns="_basis_order")
        .reset_index(drop=True)
    )


def _add_provenance(values: pd.DataFrame, context: RunContext) -> pd.DataFrame:
    output = values.copy(deep=True)
    output["run_id"] = context.run_id
    output["as_of"] = context.as_of
    output["data_vintage"] = context.data_vintage
    output["model_version"] = context.model_version
    output["config_hash"] = context.config_hash
    output["created_at"] = context.created_at
    return output


def _source_frames(
    intervals: object,
    diagnostics: object | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if diagnostics is not None:
        raise TypeError(
            "formal asset attribution publication requires an "
            "AttributionIntervalResult with validated draws"
        )
    if not isinstance(intervals, AttributionIntervalResult):
        raise TypeError(
            "intervals must be an AttributionIntervalResult with validated draws"
        )
    return intervals.intervals, intervals.diagnostics


def build_asset_attribution(
    intervals: object,
    diagnostics: object | None = None,
    *,
    context: RunContext,
) -> AssetAttributionProduct:
    """Build synchronized stable products using only RunContext provenance."""

    run_context = _validate_context(context)
    interval_source, diagnostic_source = _source_frames(intervals, diagnostics)
    normalized_intervals = _normalize_intervals(interval_source)
    normalized_diagnostics = _normalize_diagnostics(diagnostic_source)
    _validate_cross_product(normalized_intervals, normalized_diagnostics)
    attribution = _add_provenance(
        _sort_attribution(normalized_intervals), run_context
    ).loc[:, ASSET_ATTRIBUTION_COLUMNS]
    conservation = _add_provenance(
        _sort_conservation(normalized_diagnostics), run_context
    ).loc[:, ASSET_ATTRIBUTION_CONSERVATION_COLUMNS]
    product = AssetAttributionProduct(
        attribution=attribution,
        conservation=conservation,
        _validation_token=_VALIDATED_PRODUCT_TOKEN,
    )
    validate_asset_attribution(product, context=run_context)
    return product


def _validate_common_provenance(values: pd.DataFrame, context: RunContext) -> None:
    expected = {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }
    for field_name, expected_value in expected.items():
        if field_name in {"as_of", "data_vintage"}:
            actual = _normalize_dates(values[field_name], field_name)
            if not actual.eq(pd.Timestamp(expected_value)).all():
                raise ValueError(f"{field_name} does not match RunContext")
        elif field_name == "created_at":
            actual = pd.to_datetime(values[field_name], utc=True)
            if not actual.eq(pd.Timestamp(expected_value)).all():
                raise ValueError("created_at does not match RunContext")
        elif not values[field_name].eq(expected_value).all():
            raise ValueError(f"{field_name} does not match RunContext")


def _product_frames(
    product: object,
    conservation: object | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if isinstance(product, AssetAttributionProduct):
        if conservation is not None:
            raise ValueError("conservation must be omitted for AssetAttributionProduct")
        return product.attribution, product.conservation
    if not isinstance(product, pd.DataFrame) or not isinstance(
        conservation, pd.DataFrame
    ):
        raise TypeError(
            "product must be AssetAttributionProduct or two product DataFrames"
        )
    return product.copy(deep=True), conservation.copy(deep=True)


def validate_asset_attribution(
    product: object,
    conservation: object | None = None,
    *,
    context: RunContext,
) -> None:
    """Validate schemas, dimensions, semantics, conservation, and provenance."""

    run_context = _validate_context(context)
    attribution, diagnostics = _product_frames(product, conservation)
    if tuple(attribution.columns) != ASSET_ATTRIBUTION_COLUMNS:
        raise ValueError("attribution columns do not match the stable schema")
    if tuple(diagnostics.columns) != ASSET_ATTRIBUTION_CONSERVATION_COLUMNS:
        raise ValueError("conservation columns do not match the stable schema")
    interval_source = attribution.drop(columns=list(_PROVENANCE_COLUMNS))
    diagnostic_source = diagnostics.drop(columns=list(_PROVENANCE_COLUMNS))
    normalized_intervals = _normalize_intervals(interval_source)
    normalized_diagnostics = _normalize_diagnostics(diagnostic_source)
    _validate_cross_product(normalized_intervals, normalized_diagnostics)
    _validate_common_provenance(attribution, run_context)
    _validate_common_provenance(diagnostics, run_context)


def _arrow_table(values: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    arrays = [
        pa.array(values[field.name].tolist(), type=field.type, from_pandas=True)
        for field in schema
    ]
    return pa.Table.from_arrays(arrays, schema=schema)


def _require_run_directory(run_dir: Path, context: RunContext) -> None:
    try:
        run_stat = run_dir.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(run_stat.st_mode):
        raise ValueError("run_dir must be an existing real directory")
    if run_dir.name != context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _write_temporary_table(
    directory: Path,
    filename: str,
    values: pd.DataFrame,
    schema: pa.Schema,
) -> tuple[Path, tuple[int, int]]:
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{filename}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(file_descriptor, "wb") as product_file:
            descriptor_open = False
            pq.write_table(
                _arrow_table(values, schema),
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
            product_file.flush()
            os.fsync(product_file.fileno())
        if pq.read_schema(temporary_path) != schema:
            raise ValueError(f"persisted product schema mismatch: {filename}")
        temporary_stat = temporary_path.lstat()
        if not stat.S_ISREG(temporary_stat.st_mode):
            raise ValueError("temporary product must be a regular file")
        return temporary_path, (temporary_stat.st_dev, temporary_stat.st_ino)
    except BaseException:
        if descriptor_open:
            os.close(file_descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def _publish_temporary_table(
    temporary_path: Path,
    temporary_identity: tuple[int, int],
    target_path: Path,
) -> tuple[int, int]:
    try:
        os.link(temporary_path, target_path)
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite or concurrent publish of {target_path}"
        ) from error
    target_stat = target_path.lstat()
    target_identity = (target_stat.st_dev, target_stat.st_ino)
    if target_identity != temporary_identity or not stat.S_ISREG(target_stat.st_mode):
        raise ValueError("published product identity changed during publication")
    temporary_path.unlink()
    return target_identity


def _unlink_if_identity(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    if (path_stat.st_dev, path_stat.st_ino) == expected_identity:
        path.unlink()


def write_asset_attribution(
    run_dir: Path,
    product: object,
    conservation: object | None = None,
    *,
    context: RunContext,
) -> tuple[Path, Path]:
    """Exclusively write both synchronized products or clean up the pair."""

    run_context = _validate_context(context)
    directory = Path(run_dir)
    _require_run_directory(directory, run_context)
    if conservation is not None or not isinstance(product, AssetAttributionProduct):
        raise TypeError(
            "write_asset_attribution requires a product returned by "
            "build_asset_attribution"
        )
    validate_asset_attribution(product, context=run_context)
    attribution = _sort_attribution(product.attribution)
    diagnostics = _sort_conservation(product.conservation)
    attribution_path = directory / ASSET_ATTRIBUTION_FILENAME
    conservation_path = directory / ASSET_ATTRIBUTION_CONSERVATION_FILENAME
    for path in (attribution_path, conservation_path):
        if _path_entry_exists(path):
            raise FileExistsError(f"refuse accidental overwrite of {path}")
    temporary_files: list[Path] = []
    published_files: dict[Path, tuple[int, int]] = {}
    try:
        attribution_temporary, attribution_identity = _write_temporary_table(
            directory,
            ASSET_ATTRIBUTION_FILENAME,
            attribution,
            ASSET_ATTRIBUTION_SCHEMA,
        )
        temporary_files.append(attribution_temporary)
        conservation_temporary, conservation_identity = _write_temporary_table(
            directory,
            ASSET_ATTRIBUTION_CONSERVATION_FILENAME,
            diagnostics,
            ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
        )
        temporary_files.append(conservation_temporary)
        published_files[attribution_path] = _publish_temporary_table(
            attribution_temporary,
            attribution_identity,
            attribution_path,
        )
        temporary_files.remove(attribution_temporary)
        published_files[conservation_path] = _publish_temporary_table(
            conservation_temporary,
            conservation_identity,
            conservation_path,
        )
        temporary_files.remove(conservation_temporary)
    except BaseException:
        for path in temporary_files:
            path.unlink(missing_ok=True)
        for path, identity in published_files.items():
            _unlink_if_identity(path, identity)
        raise
    return attribution_path, conservation_path


def build_and_write_asset_attribution(
    run_dir: Path,
    intervals: object,
    diagnostics: object | None = None,
    *,
    context: RunContext,
) -> tuple[Path, Path]:
    """Build, validate, and exclusively write both attribution products."""

    product = build_asset_attribution(intervals, diagnostics, context=context)
    return write_asset_attribution(run_dir, product, context=context)


__all__ = [
    "ASSET_ATTRIBUTION_COLUMNS",
    "ASSET_ATTRIBUTION_CONSERVATION_COLUMNS",
    "ASSET_ATTRIBUTION_CONSERVATION_FILENAME",
    "ASSET_ATTRIBUTION_FILENAME",
    "AssetAttributionProduct",
    "build_and_write_asset_attribution",
    "build_asset_attribution",
    "validate_asset_attribution",
    "write_asset_attribution",
]
