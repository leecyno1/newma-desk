"""Stable governed ``cycle_asset_surface`` product."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seven_cycle_platform.storage import RunContext


CYCLE_ASSET_SURFACE_FILENAME = "cycle_asset_surface.parquet"
CYCLE_ASSET_SURFACE_SCHEMA = pa.schema(
    [
        pa.field("asset_id", pa.string()),
        pa.field("asset_label", pa.string()),
        pa.field("cycle_x", pa.string()),
        pa.field("cycle_y", pa.string()),
        pa.field("metric", pa.string()),
        pa.field("horizon_months", pa.int32()),
        pa.field("scenario_id", pa.string()),
        pa.field("window_months", pa.int32()),
        pa.field("grid_size", pa.int32()),
        pa.field("status", pa.string()),
        pa.field("estimator_version", pa.string()),
        pa.field("sample_count", pa.int32()),
        pa.field("bandwidth", pa.float64()),
        pa.field("oos_score", pa.float64()),
        pa.field("identifiable", pa.bool_()),
        pa.field("reason", pa.string()),
        pa.field("observations_json", pa.string()),
        pa.field("grid_json", pa.string()),
        pa.field("current_point_json", pa.string()),
        pa.field("future_path_json", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)
CYCLE_ASSET_SURFACE_COLUMNS = tuple(CYCLE_ASSET_SURFACE_SCHEMA.names)

_CYCLE_IDS = frozenset(f"C{index}" for index in range(1, 8))
_STATUSES = frozenset({"available", "not_identifiable"})
_DIMENSION_COLUMNS = (
    "asset_id",
    "horizon_months",
    "scenario_id",
    "cycle_x",
    "cycle_y",
    "metric",
    "window_months",
    "grid_size",
)
_VALIDATION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class CycleAssetSurfaceProduct:
    surfaces: pd.DataFrame
    _context: RunContext
    _validation_token: object


def _context(value: object) -> RunContext:
    if not isinstance(value, RunContext):
        raise TypeError("context must be a RunContext")
    return value


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: object, *, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


def _finite(value: object, *, name: str, allow_none: bool = False) -> float | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{name} cannot be missing")
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a finite real number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a finite real number") from error
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real number")
    return normalized


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _point(value: object, *, name: str, label_required: bool = False) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    allowed = {"x", "y", "z", "label"} if label_required else {"x", "y", "z"}
    required = allowed if label_required else {"x", "y", "z"}
    if set(value) != required:
        raise ValueError(f"{name} fields are invalid")
    normalized: dict[str, object] = {
        "x": _finite(value["x"], name=f"{name}.x"),
        "y": _finite(value["y"], name=f"{name}.y"),
        "z": _finite(value["z"], name=f"{name}.z"),
    }
    if label_required:
        normalized["label"] = _text(value["label"], name=f"{name}.label")
    return normalized


def _observations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise TypeError("observations must be a list")
    normalized: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"date", "x", "y", "z", "vintage"}:
            raise ValueError("observation fields are invalid")
        date_value = _text(item["date"], name=f"observations[{index}].date")
        try:
            normalized_date = date.fromisoformat(date_value).isoformat()
        except ValueError as error:
            raise ValueError("observation date must be ISO formatted") from error
        if normalized_date in seen_dates:
            raise ValueError("observation dates must be unique")
        seen_dates.add(normalized_date)
        normalized.append(
            {
                "date": normalized_date,
                "vintage": _text(item["vintage"], name=f"observations[{index}].vintage"),
                "x": _finite(item["x"], name=f"observations[{index}].x"),
                "y": _finite(item["y"], name=f"observations[{index}].y"),
                "z": _finite(item["z"], name=f"observations[{index}].z"),
            }
        )
    return sorted(normalized, key=lambda item: str(item["date"]))


def _grid(value: object) -> list[dict[str, float]]:
    if not isinstance(value, list):
        raise TypeError("grid must be a list")
    normalized: list[dict[str, float]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {
            "x",
            "y",
            "z",
            "lower80",
            "upper80",
            "density",
        }:
            raise ValueError("grid fields are invalid")
        point = {
            field: float(_finite(item[field], name=f"grid[{index}].{field}"))
            for field in ("x", "y", "z", "lower80", "upper80", "density")
        }
        if point["lower80"] > point["z"] or point["z"] > point["upper80"]:
            raise ValueError("grid interval must contain fitted value")
        if point["density"] < 0.0:
            raise ValueError("grid density cannot be negative")
        normalized.append(point)
    return sorted(normalized, key=lambda item: (item["x"], item["y"]))


def _normalize_surface(surface: object, context: RunContext) -> dict[str, object]:
    if not isinstance(surface, dict):
        raise TypeError("surface result must be an object")
    asset_id = _text(surface.get("asset_id"), name="asset_id")
    asset_label = _text(surface.get("asset_label"), name="asset_label")
    cycle_x = _text(surface.get("cycle_x"), name="cycle_x")
    cycle_y = _text(surface.get("cycle_y"), name="cycle_y")
    if cycle_x not in _CYCLE_IDS or cycle_y not in _CYCLE_IDS or cycle_x == cycle_y:
        raise ValueError("cycle dimensions must be distinct C1 through C7")
    metric = _text(surface.get("metric"), name="metric")
    if metric != "observed_return":
        raise ValueError("metric must be observed_return")
    horizon = _integer(surface.get("horizon_months"), name="horizon_months", minimum=1)
    scenario = _text(surface.get("scenario_id"), name="scenario_id")
    window = _integer(surface.get("window_months"), name="window_months", minimum=36)
    if window > 120:
        raise ValueError("window_months cannot exceed 120")
    grid_size = _integer(surface.get("grid_size"), name="grid_size", minimum=9)
    if grid_size > 41:
        raise ValueError("grid_size cannot exceed 41")
    status = _text(surface.get("status"), name="status")
    if status not in _STATUSES:
        raise ValueError("surface status is invalid")
    estimator_version = _text(surface.get("estimator_version"), name="estimator_version")
    observations = _observations(surface.get("observations"))
    grid = _grid(surface.get("grid"))
    evidence = surface.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "sample_count",
        "bandwidth",
        "oos_score",
        "identifiable",
        "reason",
    }:
        raise ValueError("surface evidence fields are invalid")
    sample_count = _integer(evidence["sample_count"], name="sample_count", minimum=0)
    if sample_count != len(observations):
        raise ValueError("sample_count must equal observation count")
    bandwidth = _finite(evidence["bandwidth"], name="bandwidth", allow_none=True)
    oos_score = _finite(evidence["oos_score"], name="oos_score", allow_none=True)
    if not isinstance(evidence["identifiable"], bool):
        raise TypeError("identifiable must be boolean")
    identifiable = evidence["identifiable"]
    reason = _text(evidence["reason"], name="reason")
    if status == "available":
        if not identifiable or not grid or bandwidth is None or oos_score is None:
            raise ValueError("available surface requires fitted evidence and grid")
    elif identifiable:
        raise ValueError("not_identifiable surface cannot be identifiable")
    elif grid:
        raise ValueError("not_identifiable surface cannot contain a fitted grid")
    current_point = surface.get("current_point")
    normalized_current = None if current_point is None else _point(current_point, name="current_point")
    future_path = surface.get("future_path")
    if not isinstance(future_path, list):
        raise TypeError("future_path must be a list")
    normalized_path = [
        _point(item, name=f"future_path[{index}]", label_required=True)
        for index, item in enumerate(future_path)
    ]
    return {
        "asset_id": asset_id,
        "asset_label": asset_label,
        "cycle_x": cycle_x,
        "cycle_y": cycle_y,
        "metric": metric,
        "horizon_months": horizon,
        "scenario_id": scenario,
        "window_months": window,
        "grid_size": grid_size,
        "status": status,
        "estimator_version": estimator_version,
        "sample_count": sample_count,
        "bandwidth": bandwidth,
        "oos_score": oos_score,
        "identifiable": identifiable,
        "reason": reason,
        "observations_json": _canonical_json(observations),
        "grid_json": _canonical_json(grid),
        "current_point_json": None if normalized_current is None else _canonical_json(normalized_current),
        "future_path_json": _canonical_json(normalized_path),
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }


def build_cycle_asset_surface_product(
    surfaces: Iterable[dict[str, object]],
    *,
    context: RunContext,
) -> CycleAssetSurfaceProduct:
    run_context = _context(context)
    records = [_normalize_surface(surface, run_context) for surface in surfaces]
    frame = pd.DataFrame(records, columns=CYCLE_ASSET_SURFACE_COLUMNS)
    if frame.duplicated(list(_DIMENSION_COLUMNS)).any():
        raise ValueError("duplicate surface dimensions are not allowed")
    frame = frame.sort_values(list(_DIMENSION_COLUMNS), kind="mergesort").reset_index(drop=True)
    product = CycleAssetSurfaceProduct(
        surfaces=frame,
        _context=run_context,
        _validation_token=_VALIDATION_TOKEN,
    )
    validate_cycle_asset_surface_product(product, context=run_context)
    return product


def validate_cycle_asset_surface_product(
    product: object,
    *,
    context: RunContext,
) -> None:
    run_context = _context(context)
    if not isinstance(product, CycleAssetSurfaceProduct):
        raise TypeError("product must be CycleAssetSurfaceProduct")
    if product._validation_token is not _VALIDATION_TOKEN:
        raise TypeError("product must be returned by build_cycle_asset_surface_product")
    if product._context != run_context:
        raise ValueError("product context does not match supplied RunContext")
    frame = product.surfaces
    if tuple(frame.columns) != CYCLE_ASSET_SURFACE_COLUMNS:
        raise ValueError("surface product columns changed")
    if frame.duplicated(list(_DIMENSION_COLUMNS)).any():
        raise ValueError("duplicate surface dimensions are not allowed")
    for row in frame.to_dict(orient="records"):
        if row["run_id"] != run_context.run_id or row["config_hash"] != run_context.config_hash:
            raise ValueError("surface product provenance does not match context")
        observations = json.loads(row["observations_json"])
        grid = json.loads(row["grid_json"])
        future_path = json.loads(row["future_path_json"])
        current_point = None if row["current_point_json"] is None else json.loads(row["current_point_json"])
        rebuilt = {
            "asset_id": row["asset_id"],
            "asset_label": row["asset_label"],
            "cycle_x": row["cycle_x"],
            "cycle_y": row["cycle_y"],
            "metric": row["metric"],
            "horizon_months": int(row["horizon_months"]),
            "scenario_id": row["scenario_id"],
            "window_months": int(row["window_months"]),
            "grid_size": int(row["grid_size"]),
            "status": row["status"],
            "estimator_version": row["estimator_version"],
            "observations": observations,
            "grid": grid,
            "current_point": current_point,
            "future_path": future_path,
            "evidence": {
                "sample_count": int(row["sample_count"]),
                "bandwidth": None if pd.isna(row["bandwidth"]) else float(row["bandwidth"]),
                "oos_score": None if pd.isna(row["oos_score"]) else float(row["oos_score"]),
                "identifiable": bool(row["identifiable"]),
                "reason": row["reason"],
            },
        }
        normalized = _normalize_surface(rebuilt, run_context)
        for field in CYCLE_ASSET_SURFACE_COLUMNS:
            expected = normalized[field]
            actual = row[field]
            if pd.isna(actual) and expected is None:
                continue
            if actual != expected:
                raise ValueError(f"surface product field changed: {field}")


def _arrow_table(frame: pd.DataFrame) -> pa.Table:
    arrays = [
        pa.array(frame[field.name].tolist(), type=field.type, from_pandas=True)
        for field in CYCLE_ASSET_SURFACE_SCHEMA
    ]
    return pa.Table.from_arrays(arrays, schema=CYCLE_ASSET_SURFACE_SCHEMA)


def write_cycle_asset_surface_product(
    run_dir: Path,
    product: CycleAssetSurfaceProduct,
    *,
    context: RunContext,
) -> Path:
    run_context = _context(context)
    directory = Path(run_dir)
    try:
        run_stat = directory.lstat()
    except OSError as error:
        raise ValueError("run_dir must be an existing real directory") from error
    if not stat.S_ISDIR(run_stat.st_mode) or directory.name != run_context.run_id:
        raise ValueError("run_dir name must match RunContext run_id")
    validate_cycle_asset_surface_product(product, context=run_context)
    target = directory / CYCLE_ASSET_SURFACE_FILENAME
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"refuse accidental overwrite of {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=directory,
        prefix=f".{CYCLE_ASSET_SURFACE_FILENAME}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as product_file:
            descriptor_open = False
            pq.write_table(
                _arrow_table(product.surfaces),
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
            )
            product_file.flush()
            os.fsync(product_file.fileno())
        if pq.read_schema(temporary) != CYCLE_ASSET_SURFACE_SCHEMA:
            raise ValueError("persisted surface product schema mismatch")
        os.link(temporary, target)
        linked = True
        temporary.unlink()
        return target
    except FileExistsError as error:
        raise FileExistsError(
            f"refuse accidental overwrite or concurrent publish of {target}"
        ) from error
    except BaseException:
        if linked:
            target.unlink(missing_ok=True)
        raise
    finally:
        if descriptor_open:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


__all__ = [
    "CYCLE_ASSET_SURFACE_COLUMNS",
    "CYCLE_ASSET_SURFACE_FILENAME",
    "CYCLE_ASSET_SURFACE_SCHEMA",
    "CycleAssetSurfaceProduct",
    "build_cycle_asset_surface_product",
    "validate_cycle_asset_surface_product",
    "write_cycle_asset_surface_product",
]
