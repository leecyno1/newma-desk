"""Stable ``cycle_phase_vintage`` product construction and persistence."""

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from numbers import Real
from pathlib import Path
import stat

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.contracts.arrow import CYCLE_PHASE_VINTAGE_SCHEMA
from seven_cycle_platform.cycles.phase import CyclePhase, phase_from_level_slope
from seven_cycle_platform.storage.run_context import RunContext
from seven_cycle_platform.types import VintageKind


CYCLE_PHASE_VINTAGE_FILENAME = "cycle_phase_vintage.parquet"
CYCLE_PHASE_VINTAGE_COLUMNS = tuple(CYCLE_PHASE_VINTAGE_SCHEMA.names)
_CYCLE_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
_DIMENSION_COLUMNS = ("date", "cycle_id", "vintage")
_STATE_COLUMNS = (
    "angle",
    "phase",
    "level",
    "slope",
    "amplitude",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
)
_CORE_STATE_COLUMNS = (
    "angle",
    "phase",
    "level",
    "slope",
    "amplitude",
    "uncertainty",
)
_PROVENANCE_COLUMNS = (
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
)
_GOVERNED_ENGINE_COLUMNS = {
    "frequency",
    "acceleration",
    "innovation",
    "evidence_level",
    "usage_status",
    "effective_cycles",
    "observed_observations",
    "member_breadth",
    "category_breadth",
    "total_members",
    "total_categories",
}
_SOURCE_COLUMNS = {
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    *_STATE_COLUMNS,
    *_GOVERNED_ENGINE_COLUMNS,
}
_VINTAGE_ORDER = {
    VintageKind.REALTIME.value: 0,
    VintageKind.LATEST_HISTORICAL.value: 1,
    VintageKind.PSEUDO_VINTAGE.value: 2,
}
_SUPPORTED_PRODUCT_VINTAGES = frozenset(
    {
        VintageKind.REALTIME,
        VintageKind.LATEST_HISTORICAL,
        VintageKind.PSEUDO_VINTAGE,
    }
)


def _normalize_date(value: object, *, name: str) -> pd.Timestamp:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} cannot be a boolean; a date is required")
    if isinstance(value, pd.Timestamp):
        timestamp = value
    elif isinstance(value, (date, datetime, np.datetime64, str)):
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must contain valid dates") from error
    else:
        raise TypeError(f"{name} must contain date values")
    if pd.isna(timestamp):
        raise ValueError(f"{name} cannot contain missing dates")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone.utc).tz_localize(None)
    return timestamp.normalize()


def _normalize_dates(values: pd.Series, *, name: str) -> pd.Series:
    normalized = [_normalize_date(value, name=name) for value in values.tolist()]
    return pd.Series(normalized, index=values.index, dtype="datetime64[ns]")


def _normalize_real(value: object, *, name: str) -> float:
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and missing:
        return np.nan
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (Real, np.integer, np.floating),
    ):
        raise TypeError(f"{name} must contain real numbers or missing values")
    numeric = float(value)
    if not np.isfinite(numeric):
        raise ValueError(f"{name} must contain finite values or missing values")
    return numeric


def _normalize_real_column(values: pd.Series, *, name: str) -> pd.Series:
    return pd.Series(
        [_normalize_real(value, name=name) for value in values.tolist()],
        index=values.index,
        dtype="float64",
    )


def _normalize_cycle_ids(values: pd.Series) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if not isinstance(value, str):
            raise TypeError("cycle_id must contain strings")
        if value not in _CYCLE_IDS:
            raise ValueError(f"unknown cycle_id: {value}")
        normalized.append(value)
    return pd.Series(normalized, index=values.index, dtype="object")


def _normalize_vintages(values: pd.Series) -> pd.Series:
    normalized: list[str] = []
    for value in values.tolist():
        if isinstance(value, VintageKind):
            vintage = value
        else:
            if not isinstance(value, str):
                raise TypeError("vintage must contain VintageKind strings")
            try:
                vintage = VintageKind(value)
            except ValueError as error:
                raise ValueError(f"unknown vintage: {value}") from error
        if vintage not in _SUPPORTED_PRODUCT_VINTAGES:
            raise ValueError(
                "cycle_phase_vintage product does not support data-identity "
                f"vintage: {vintage.value}"
            )
        normalized.append(vintage.value)
    return pd.Series(normalized, index=values.index, dtype="object")


def _normalize_caveats(values: pd.Series, vintages: pd.Series) -> pd.Series:
    normalized: list[str | None] = []
    for value, vintage in zip(values.tolist(), vintages.tolist(), strict=True):
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            caveat = None
        elif isinstance(value, str) and value.strip():
            caveat = value.strip()
        else:
            raise TypeError("vintage_caveat must contain strings or missing values")
        if vintage == VintageKind.PSEUDO_VINTAGE.value and caveat is None:
            raise ValueError("pseudo_vintage rows require an explicit caveat")
        normalized.append(caveat)
    return pd.Series(normalized, index=values.index, dtype="object")


def _state_frames(states: object) -> tuple[pd.DataFrame, ...]:
    if isinstance(states, pd.DataFrame):
        frames = (states,)
    elif isinstance(states, Mapping):
        normalized_frames: list[pd.DataFrame] = []
        for vintage, frame in sorted(states.items(), key=lambda item: str(item[0])):
            if not isinstance(frame, pd.DataFrame):
                raise TypeError("state mappings must contain pandas DataFrames")
            copied = frame.copy(deep=True)
            normalized_vintage = (
                vintage.value if isinstance(vintage, VintageKind) else str(vintage)
            )
            if "vintage" in copied:
                if not copied["vintage"].eq(normalized_vintage).all():
                    raise ValueError("state mapping key must match the vintage column")
            else:
                copied["vintage"] = normalized_vintage
            normalized_frames.append(copied)
        frames = tuple(normalized_frames)
    elif isinstance(states, Iterable) and not isinstance(
        states,
        (str, bytes, bytearray),
    ):
        frames = tuple(states)
    else:
        raise TypeError("states must be a DataFrame or iterable of DataFrames")
    if not frames:
        raise ValueError("states must contain at least one DataFrame")
    if any(not isinstance(frame, pd.DataFrame) for frame in frames):
        raise TypeError("states must contain only pandas DataFrames")
    return tuple(frame.copy(deep=True) for frame in frames)


def _normalize_state_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.columns.has_duplicates:
        raise ValueError("state frame columns must be unique")
    if frame.index.has_duplicates:
        raise ValueError("state frame index must be unique")
    values = frame.copy(deep=True)
    prohibited = set(_PROVENANCE_COLUMNS).intersection(values.columns)
    if "as_of" in prohibited and "date" not in values.columns:
        values = values.rename(columns={"as_of": "date"})
        prohibited.remove("as_of")
    if prohibited:
        names = ", ".join(sorted(prohibited))
        raise ValueError(
            "product provenance must come only from RunContext; "
            f"remove {names}"
        )
    if "date" in values.columns and "as_of" in values.columns:
        raise ValueError(
            "product provenance must come only from RunContext; remove as_of"
        )
    unexpected = sorted(set(values.columns).difference(_SOURCE_COLUMNS))
    if unexpected:
        raise ValueError(
            "unexpected state columns: " + ", ".join(map(str, unexpected))
        )
    required = {
        "date",
        "cycle_id",
        "vintage",
        *_STATE_COLUMNS,
    }
    missing = sorted(required.difference(values.columns))
    if missing:
        raise ValueError("missing required state columns: " + ", ".join(missing))
    if "vintage_caveat" not in values.columns:
        values["vintage_caveat"] = None

    values["date"] = _normalize_dates(values["date"], name="date")
    values["cycle_id"] = _normalize_cycle_ids(values["cycle_id"])
    values["vintage"] = _normalize_vintages(values["vintage"])
    values["vintage_caveat"] = _normalize_caveats(
        values["vintage_caveat"],
        values["vintage"],
    )
    for field_name in _STATE_COLUMNS:
        if field_name == "phase":
            continue
        values[field_name] = _normalize_real_column(
            values[field_name],
            name=field_name,
        )

    allowed_phases = {phase.value for phase in CyclePhase}
    phases: list[str | None] = []
    for phase in values["phase"].tolist():
        missing_phase = pd.isna(phase)
        if isinstance(missing_phase, (bool, np.bool_)) and missing_phase:
            phases.append(None)
        elif isinstance(phase, CyclePhase):
            phases.append(phase.value)
        elif isinstance(phase, str) and phase in allowed_phases:
            phases.append(phase)
        else:
            raise ValueError("phase must contain governed phase labels or missing")
    values["phase"] = pd.Series(phases, index=values.index, dtype="object")

    missingness = pd.DataFrame(
        {
            field_name: values[field_name].isna()
            for field_name in _CORE_STATE_COLUMNS
        },
        index=values.index,
    )
    if not (missingness.all(axis=1) | ~missingness.any(axis=1)).all():
        raise ValueError("state missingness must align across governed fields")
    available = ~missingness.all(axis=1)
    for row_index in values.index[available]:
        expected_phase = phase_from_level_slope(
            values.at[row_index, "level"],
            values.at[row_index, "slope"],
        )
        if expected_phase is None or values.at[row_index, "phase"] != expected_phase.value:
            raise ValueError("phase must align with level and slope")

    if not values.loc[values["angle"].notna(), "angle"].between(
        0.0,
        360.0,
        inclusive="left",
    ).all():
        raise ValueError("angle must be in [0, 360)")
    for field_name in ("amplitude", "uncertainty"):
        finite = values.loc[values[field_name].notna(), field_name]
        if not finite.ge(0.0).all():
            raise ValueError(f"{field_name} must be nonnegative")
    for field_name in ("center_period", "bandwidth"):
        if values[field_name].isna().any() or not values[field_name].gt(0.0).all():
            raise ValueError(f"{field_name} must be positive and present")
    if values["confidence"].isna().any() or not values["confidence"].between(
        0.0,
        1.0,
    ).all():
        raise ValueError("confidence must be present and between 0 and 1")
    return values.loc[:, [
        "date",
        "cycle_id",
        "vintage",
        "vintage_caveat",
        *_STATE_COLUMNS,
    ]]


def _validate_dimensions(values: pd.DataFrame) -> None:
    if values.duplicated(list(_DIMENSION_COLUMNS)).any():
        raise ValueError("date × cycle_id × vintage dimensions must be unique")
    for (row_date, vintage), group in values.groupby(
        ["date", "vintage"],
        sort=False,
    ):
        cycle_ids = tuple(
            sorted(group["cycle_id"], key=lambda value: int(value[1:]))
        )
        if cycle_ids != _CYCLE_IDS:
            raise ValueError(
                "every date × vintage view must contain exactly C1 through C7; "
                f"invalid group {row_date.date()} {vintage}"
            )


def _sort_product(values: pd.DataFrame) -> pd.DataFrame:
    cycle_order = values["cycle_id"].str.removeprefix("C").astype("int64")
    vintage_order = values["vintage"].map(_VINTAGE_ORDER).astype("int64")
    return (
        values.assign(
            _cycle_order=cycle_order,
            _vintage_order=vintage_order,
        )
        .sort_values(
            ["date", "_vintage_order", "_cycle_order"],
            kind="stable",
        )
        .drop(columns=["_cycle_order", "_vintage_order"])
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
    return output.loc[:, CYCLE_PHASE_VINTAGE_COLUMNS]


def _validate_context(context: object) -> RunContext:
    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    return context


def build_cycle_phase_vintage(
    states: object,
    *,
    context: RunContext,
) -> pd.DataFrame:
    """Build the stable date × cycle × vintage product from state views."""

    run_context = _validate_context(context)
    normalized = pd.concat(
        [_normalize_state_frame(frame) for frame in _state_frames(states)],
        ignore_index=True,
    )
    _validate_dimensions(normalized)
    product = _add_provenance(_sort_product(normalized), run_context)
    validate_cycle_phase_vintage(product, context=run_context)
    return product


def _validate_common_provenance(
    values: pd.DataFrame,
    context: RunContext,
) -> None:
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
            actual = _normalize_dates(values[field_name], name=field_name)
            target = pd.Timestamp(expected_value)
            if not actual.eq(target).all():
                raise ValueError(f"{field_name} does not match RunContext")
        elif field_name == "created_at":
            actual = pd.to_datetime(values[field_name], utc=True)
            if not actual.eq(pd.Timestamp(expected_value)).all():
                raise ValueError("created_at does not match RunContext")
        elif not values[field_name].eq(expected_value).all():
            raise ValueError(f"{field_name} does not match RunContext")


def validate_cycle_phase_vintage(
    product: pd.DataFrame,
    *,
    context: RunContext,
) -> None:
    """Validate stable columns, dimensions, values, and RunContext provenance."""

    run_context = _validate_context(context)
    if not isinstance(product, pd.DataFrame):
        raise TypeError("product must be a pandas DataFrame")
    if product.columns.has_duplicates:
        raise ValueError("product columns must be unique")
    if tuple(product.columns) != CYCLE_PHASE_VINTAGE_COLUMNS:
        raise ValueError("product columns do not match the stable schema")
    state_values = _normalize_state_frame(
        product.loc[:, [
            "date",
            "cycle_id",
            "vintage",
            "vintage_caveat",
            *_STATE_COLUMNS,
        ]]
    )
    _validate_dimensions(state_values)
    _validate_common_provenance(product, run_context)


def _arrow_table(product: pd.DataFrame) -> pa.Table:
    arrays = [
        pa.array(
            product[field.name].tolist(),
            type=field.type,
            from_pandas=True,
        )
        for field in CYCLE_PHASE_VINTAGE_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=CYCLE_PHASE_VINTAGE_SCHEMA)


def _require_run_directory(run_dir: Path, context: RunContext) -> None:
    try:
        run_stat = run_dir.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(run_stat.st_mode):
        raise ValueError("run_dir must be an existing real directory")
    if run_dir.name != context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")


def write_cycle_phase_vintage(
    run_dir: Path,
    product: pd.DataFrame,
    *,
    context: RunContext,
) -> Path:
    """Write the stable Parquet product exclusively under the current run."""

    run_context = _validate_context(context)
    directory = Path(run_dir)
    _require_run_directory(directory, run_context)
    validate_cycle_phase_vintage(product, context=run_context)
    canonical_product = _sort_product(product.copy(deep=True))
    product_path = directory / CYCLE_PHASE_VINTAGE_FILENAME
    try:
        product_file = product_path.open("xb")
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite of {product_path}"
        ) from error
    try:
        with product_file:
            pq.write_table(
                _arrow_table(canonical_product),
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
        if pq.read_schema(product_path) != CYCLE_PHASE_VINTAGE_SCHEMA:
            raise ValueError("persisted cycle product schema mismatch")
    except BaseException:
        product_path.unlink(missing_ok=True)
        raise
    return product_path


def build_and_write_cycle_phase_vintage(
    run_dir: Path,
    states: object,
    *,
    context: RunContext,
) -> Path:
    """Build, validate, and exclusively write ``cycle_phase_vintage``."""

    product = build_cycle_phase_vintage(states, context=context)
    return write_cycle_phase_vintage(run_dir, product, context=context)


__all__ = [
    "CYCLE_PHASE_VINTAGE_COLUMNS",
    "CYCLE_PHASE_VINTAGE_FILENAME",
    "build_and_write_cycle_phase_vintage",
    "build_cycle_phase_vintage",
    "validate_cycle_phase_vintage",
    "write_cycle_phase_vintage",
]
