"""Stable governed research audit products."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import os
from pathlib import Path
import stat
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.storage import RunContext


PROVENANCE_FIELDS = [
    pa.field("run_id", pa.string(), nullable=False),
    pa.field("as_of", pa.date32(), nullable=False),
    pa.field("data_vintage", pa.date32(), nullable=False),
    pa.field("model_version", pa.string(), nullable=False),
    pa.field("config_hash", pa.string(), nullable=False),
    pa.field("created_at", pa.timestamp("us", tz="UTC"), nullable=False),
]

CYCLE_EVIDENCE_FILENAME = "cycle_evidence.parquet"
CYCLE_EVIDENCE_SCHEMA = pa.schema(
    [
        pa.field("cycle_id", pa.string(), nullable=False),
        pa.field("evidence_status", pa.string(), nullable=False),
        pa.field("center_prior_months", pa.float64(), nullable=False),
        pa.field("empirical_min_months", pa.float64()),
        pa.field("empirical_max_months", pa.float64()),
        pa.field("family_centers_json", pa.string(), nullable=False),
        pa.field("reason_codes_json", pa.string(), nullable=False),
        pa.field("summary", pa.string(), nullable=False),
        *PROVENANCE_FIELDS,
    ]
)

DATA_IDENTITY_FILENAME = "data_identity.parquet"
DATA_IDENTITY_SCHEMA = pa.schema(
    [
        pa.field("entity_id", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("frequency", pa.string(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("transform", pa.string(), nullable=False),
        pa.field("observation_start", pa.date32(), nullable=False),
        pa.field("source_data_as_of", pa.date32(), nullable=False),
        pa.field("release_date", pa.date32(), nullable=False),
        pa.field(
            "retrieval_time",
            pa.timestamp("us", tz="UTC"),
            nullable=False,
        ),
        pa.field("vintage_kind", pa.string(), nullable=False),
        pa.field("stale_months", pa.int32(), nullable=False),
        pa.field("stale_after_months", pa.int32(), nullable=False),
        pa.field("freshness_status", pa.string(), nullable=False),
        pa.field("proxy_for", pa.string()),
        pa.field("caveat", pa.string(), nullable=False),
        *PROVENANCE_FIELDS,
    ]
)

PUBLICATION_GATE_FILENAME = "publication_gate.parquet"
PUBLICATION_GATE_SCHEMA = pa.schema(
    [
        pa.field("cycle_id", pa.string(), nullable=False),
        pa.field("layer", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("reason_codes_json", pa.string(), nullable=False),
        *PROVENANCE_FIELDS,
    ]
)

CALIBRATION_LOG_FILENAME = "calibration_log.parquet"
CALIBRATION_LOG_SCHEMA = pa.schema(
    [
        pa.field("calibration_date", pa.date32(), nullable=False),
        pa.field("subject_id", pa.string(), nullable=False),
        pa.field("version", pa.string(), nullable=False),
        pa.field("change_summary", pa.string(), nullable=False),
        pa.field("impact_summary", pa.string(), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        *PROVENANCE_FIELDS,
    ]
)

_PROVENANCE_NAMES = frozenset(field.name for field in PROVENANCE_FIELDS)
_PROVENANCE_FIELD_COUNT = len(PROVENANCE_FIELDS)
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_GOVERNED_SCHEMAS = {
    CYCLE_EVIDENCE_FILENAME: CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME: DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME: PUBLICATION_GATE_SCHEMA,
    CALIBRATION_LOG_FILENAME: CALIBRATION_LOG_SCHEMA,
}
_SORT_KEYS = {
    CYCLE_EVIDENCE_FILENAME: ("cycle_id",),
    DATA_IDENTITY_FILENAME: ("entity_id",),
    PUBLICATION_GATE_FILENAME: ("cycle_id", "layer"),
    CALIBRATION_LOG_FILENAME: ("calibration_date", "subject_id", "version"),
}


def _validate_context(context: object) -> RunContext:
    if not isinstance(context, RunContext):
        raise TypeError("context must be a RunContext")
    return context


def _validate_product_contract(filename: object, schema: object) -> pa.Schema:
    if not isinstance(filename, str):
        raise TypeError("filename must be a string")
    if not isinstance(schema, pa.Schema):
        raise TypeError("schema must be a pyarrow Schema")
    expected_schema = _GOVERNED_SCHEMAS.get(filename)
    if expected_schema is None:
        raise ValueError(f"unsupported governance product filename: {filename}")
    if not schema.equals(expected_schema, check_metadata=True):
        raise ValueError(f"schema does not match governed product {filename}")
    return expected_schema


def _validate_value(value: object, field: pa.Field, *, row_index: int) -> None:
    if value is None:
        if field.nullable:
            return
        raise ValueError(f"records[{row_index}].{field.name} cannot be null")
    field_type = field.type
    field_path = f"records[{row_index}].{field.name}"
    if pa.types.is_string(field_type):
        if not isinstance(value, str):
            raise TypeError(f"{field_path} must be string")
        return
    if pa.types.is_float64(field_type):
        if type(value) is not float:
            raise TypeError(f"{field_path} must be float64")
        if not math.isfinite(value):
            raise ValueError(f"{field_path} must be finite")
        return
    if pa.types.is_int32(field_type):
        if type(value) is not int:
            raise TypeError(f"{field_path} must be int32")
        if value < _INT32_MIN or value > _INT32_MAX:
            raise ValueError(f"{field_path} exceeds int32 range")
        return
    if pa.types.is_date32(field_type):
        if type(value) is not date:
            raise TypeError(f"{field_path} must be date32")
        return
    if pa.types.is_timestamp(field_type):
        if type(value) is not datetime:
            raise TypeError(f"{field_path} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_path} must be timezone-aware")
        if field_type.tz == "UTC" and value.utcoffset() != timedelta(0):
            raise ValueError(f"{field_path} must use UTC")
        return
    raise TypeError(f"unsupported governed field type: {field_type}")


def _validated_rows(
    records: object,
    schema: pa.Schema,
    context: RunContext,
) -> list[dict[str, object]]:
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    product_fields = pa.schema(list(schema)[:-_PROVENANCE_FIELD_COUNT])
    expected_names = frozenset(product_fields.names)
    provenance = {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }
    rows: list[dict[str, object]] = []
    for row_index, record in enumerate(records):
        if type(record) is not dict:
            raise TypeError(f"records[{row_index}] must be a dictionary")
        if any(not isinstance(name, str) for name in record):
            raise TypeError(f"records[{row_index}] field names must be strings")
        caller_provenance = sorted(_PROVENANCE_NAMES.intersection(record))
        if caller_provenance:
            fields = ", ".join(caller_provenance)
            raise ValueError(
                "product provenance must come only from RunContext; "
                f"remove fields: {fields}"
            )
        record_names = frozenset(record)
        missing_names = sorted(expected_names - record_names)
        if missing_names:
            raise ValueError(
                f"records[{row_index}] missing fields: {', '.join(missing_names)}"
            )
        unexpected_names = sorted(record_names - expected_names)
        if unexpected_names:
            raise ValueError(
                f"records[{row_index}] unexpected fields: {', '.join(unexpected_names)}"
            )
        for field in product_fields:
            _validate_value(record[field.name], field, row_index=row_index)
        rows.append({**record, **provenance})
    return rows


def _sort_value(value: object) -> tuple[int, str]:
    if value is None:
        return 0, ""
    if isinstance(value, datetime):
        return 1, value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return 1, value.isoformat()
    if isinstance(value, float):
        return 1, value.hex()
    return 1, str(value)


def _canonicalize_rows(
    rows: list[dict[str, object]],
    *,
    filename: str,
    schema: pa.Schema,
) -> list[dict[str, object]]:
    primary_keys = _SORT_KEYS[filename]
    business_names = schema.names[:-_PROVENANCE_FIELD_COUNT]
    tie_breakers = tuple(name for name in business_names if name not in primary_keys)
    sort_names = (*primary_keys, *tie_breakers)
    return sorted(
        rows,
        key=lambda row: tuple(_sort_value(row[name]) for name in sort_names),
    )


def _require_run_directory(run_dir: Path, context: RunContext) -> None:
    try:
        directory_stat = run_dir.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError("run_dir must be an existing real directory")
    if run_dir.name != context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _fsync_directory(directory: Path) -> None:
    directory_descriptor = os.open(
        directory,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _unlink_if_identity(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    if (path_stat.st_dev, path_stat.st_ino) == expected_identity:
        path.unlink()


def _write_table_exclusive(
    run_dir: Path,
    *,
    filename: str,
    schema: pa.Schema,
    table: pa.Table,
) -> Path:
    target = run_dir / filename
    if _path_entry_exists(target):
        raise FileExistsError(f"refuse accidental overwrite of {target}")
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=run_dir,
        prefix=f".{filename}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    linked_identity: tuple[int, int] | None = None
    try:
        with os.fdopen(file_descriptor, "wb") as product_file:
            descriptor_open = False
            pq.write_table(
                table,
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
            product_file.flush()
            os.fsync(product_file.fileno())
        if not pq.read_schema(temporary).equals(schema, check_metadata=False):
            raise ValueError(
                f"persisted governance product schema mismatch: {filename}"
            )
        temporary_stat = temporary.lstat()
        if not stat.S_ISREG(temporary_stat.st_mode):
            raise ValueError("temporary product must be a regular file")
        temporary_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            raise FileExistsError(
                f"refuse accidental overwrite or concurrent publish of {target}"
            ) from error
        linked_identity = temporary_identity
        target_stat = target.lstat()
        target_identity = (target_stat.st_dev, target_stat.st_ino)
        if target_identity != temporary_identity or not stat.S_ISREG(
            target_stat.st_mode
        ):
            raise ValueError("published governance product identity changed")
        temporary.unlink()
        _fsync_directory(run_dir)
        return target
    except BaseException:
        if linked_identity is not None:
            _unlink_if_identity(target, linked_identity)
        raise
    finally:
        if descriptor_open:
            os.close(file_descriptor)
        temporary.unlink(missing_ok=True)


def write_records(
    run_dir: Path,
    *,
    filename: str,
    schema: pa.Schema,
    records: list[dict[str, object]],
    context: RunContext,
) -> Path:
    """Validate, add RunContext provenance, and exclusively write one product."""

    run_context = _validate_context(context)
    governed_schema = _validate_product_contract(filename, schema)
    directory = Path(run_dir)
    _require_run_directory(directory, run_context)
    rows = _validated_rows(records, governed_schema, run_context)
    canonical_rows = _canonicalize_rows(
        rows,
        filename=filename,
        schema=governed_schema,
    )
    table = pa.Table.from_pylist(canonical_rows, schema=governed_schema)
    if not table.schema.equals(governed_schema, check_metadata=False):
        raise ValueError(f"governance product schema mismatch: {filename}")
    return _write_table_exclusive(
        directory,
        filename=filename,
        schema=governed_schema,
        table=table,
    )


__all__ = [
    "CALIBRATION_LOG_FILENAME",
    "CALIBRATION_LOG_SCHEMA",
    "CYCLE_EVIDENCE_FILENAME",
    "CYCLE_EVIDENCE_SCHEMA",
    "DATA_IDENTITY_FILENAME",
    "DATA_IDENTITY_SCHEMA",
    "PROVENANCE_FIELDS",
    "PUBLICATION_GATE_FILENAME",
    "PUBLICATION_GATE_SCHEMA",
    "write_records",
]
