"""Publish the approved Phase A research foundation run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, TypeVar

import pandas as pd
from pydantic import BaseModel, ValidationError
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from seven_cycle_platform.contracts.arrow import CYCLE_PHASE_VINTAGE_SCHEMA
from seven_cycle_platform.cycles.phase import phase_from_level_slope
from seven_cycle_platform.data.identity import DataIdentity
from seven_cycle_platform.governance.baseline import (
    EvidenceBaseline,
    _UniqueKeySafeLoader,
)
from seven_cycle_platform.governance.gates import GateInput, evaluate_gate
from seven_cycle_platform.products.cycle_phase import CYCLE_PHASE_VINTAGE_FILENAME
from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_FILENAME,
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME,
    DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME,
    PUBLICATION_GATE_SCHEMA,
    write_records,
)
from seven_cycle_platform.registry.loader import (
    RegistryLoadError,
    _validate_assets,
    _validate_channels,
    _validate_cycles,
    _validate_indicators,
)
from seven_cycle_platform.registry.models import (
    AssetRegistry,
    ChannelRegistry,
    CycleRegistry,
    IndicatorRegistry,
    RegistryBundle,
)
from seven_cycle_platform.storage.publisher import publish_run
from seven_cycle_platform.storage.run_context import RunContext, canonical_json_bytes
from seven_cycle_platform.types import PublicationGateStatus, VintageKind


_APPROVED_AS_OF = date(2026, 7, 19)
_DATA_VINTAGE = date(2025, 12, 31)
_RESEARCH_LAYERS = (
    "historical",
    "realtime",
    "forecast",
    "asset_statistics",
)
_VINTAGE_CAVEAT = (
    "Two-sided Gaussian and Butterworth historical estimate; "
    "endpoint is not a realtime signal."
)
_PROJECT_ROOT = Path(__file__).resolve(strict=True).parents[3]
_APPROVED_CONFIG_ROOT = (
    _PROJECT_ROOT / "config" / "seven_cycle" / "approved" / "2026-07-19"
)
_APPROVED_SOURCE_SPECS = {
    "asset_registry": (
        "assets.yaml",
        "e8670f75f792c0f74bd02fdae338eba45c3b16203036c55d0b88a7ea7bbd7839",
    ),
    "channel_registry": (
        "channels.yaml",
        "ee0f1aa00bba7f0448dc45fd6376b4b73f7300f24662aeeb11837ab2e352e7ef",
    ),
    "cycle_registry": (
        "cycles.yaml",
        "25e765a3d11e68051e1f065f7caf01e14abbb054d3121d5af687b7d0184d3a8e",
    ),
    "indicator_registry": (
        "indicators.yaml",
        "3f08e14f740376fdfc42f8ce4b45736dc2a7acb72cbf65f53d5867b7259440ae",
    ),
    "evidence_baseline": (
        "evidence_baseline.yaml",
        "cd31c31c5f339fc5d72facf137dc387c27660302267a86b9ad86d07ab7eb9aff",
    ),
    "historical_prototype": (
        "c4_c5_phase_display_prototype_2026-07-19.json",
        "2908150566e426e97795cd2ca64fedcb2cc78f02c9e3e817cfe851988331449c",
    ),
    "realtime_prototype": (
        "c4_pseudo_realtime_prototype_2026-07-19.json",
        "657e0c03bbc5f508a3df3fd89db5a95d6bcd1d152af1cfa993953626b73fbea1",
    ),
    "forecast_prototype": (
        "c4_forecast_prototype_2026-07-19.json",
        "30bd8ea091e7e886b326fbf25568fdb528d2efe5563573f544e6169888d33e38",
    ),
    "asset_prototype": (
        "c4_asset_statistics_prototype_2026-07-19.json",
        "bd304dd97134687e66fc669912800c6f00555b50b5653eea883350601549e218",
    ),
}
_EXPECTED_SOURCE_PATHS = {
    "asset_registry": _APPROVED_CONFIG_ROOT / "assets.yaml",
    "channel_registry": _APPROVED_CONFIG_ROOT / "channels.yaml",
    "cycle_registry": _APPROVED_CONFIG_ROOT / "cycles.yaml",
    "indicator_registry": (
        _APPROVED_CONFIG_ROOT / "indicators.yaml"
    ),
    "evidence_baseline": (
        _APPROVED_CONFIG_ROOT / "evidence_baseline.yaml"
    ),
    "historical_prototype": (
        _PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
    ),
    "realtime_prototype": (
        _PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
    ),
    "forecast_prototype": (
        _PROJECT_ROOT / "output" / "c4_forecast_prototype_2026-07-19.json"
    ),
    "asset_prototype": (
        _PROJECT_ROOT / "output" / "c4_asset_statistics_prototype_2026-07-19.json"
    ),
}
_RegistryFileModel = TypeVar("_RegistryFileModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class FoundationSources:
    config_dir: Path
    evidence_path: Path
    historical_path: Path
    realtime_path: Path
    forecast_path: Path
    asset_path: Path


@dataclass(frozen=True, slots=True)
class FoundationBuildResult:
    run_id: str
    run_dir: Path


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    role: str
    filename: str
    content: bytes
    checksum: str


def _snapshot_label(snapshot: _SourceSnapshot) -> str:
    return f"{snapshot.role} ({snapshot.filename})"


def _load_json(snapshot: _SourceSnapshot) -> dict[str, Any]:
    label = _snapshot_label(snapshot)
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label}: invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: JSON input must contain an object")
    return payload


def _canonical_json(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _source_paths(sources: FoundationSources) -> dict[str, Path]:
    config_dir = Path(sources.config_dir)
    paths = {
        "asset_registry": config_dir / "assets.yaml",
        "channel_registry": config_dir / "channels.yaml",
        "cycle_registry": config_dir / "cycles.yaml",
        "indicator_registry": config_dir / "indicators.yaml",
        "evidence_baseline": Path(sources.evidence_path),
        "historical_prototype": Path(sources.historical_path),
        "realtime_prototype": Path(sources.realtime_path),
        "forecast_prototype": Path(sources.forecast_path),
        "asset_prototype": Path(sources.asset_path),
    }
    names = [path.name for path in paths.values()]
    if len(names) != len(set(names)):
        raise ValueError("foundation source filenames must be unique")
    return paths


def _snapshot_approved_sources(
    sources: FoundationSources,
) -> dict[str, _SourceSnapshot]:
    source_paths = _source_paths(sources)
    snapshots: dict[str, _SourceSnapshot] = {}
    for role, (expected_filename, expected_checksum) in _APPROVED_SOURCE_SPECS.items():
        source_path = source_paths[role]
        if source_path.name != expected_filename:
            raise ValueError(f"{role} must use approved filename {expected_filename}")
        try:
            before = source_path.lstat()
        except OSError as error:
            raise ValueError(f"{role} source path is missing or unreadable") from error
        if stat.S_ISLNK(before.st_mode):
            raise ValueError(f"{role} source path must not be a symlink")
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{role} source path must be a regular file")
        expected_path = _EXPECTED_SOURCE_PATHS[role]
        lexical_path = Path(os.path.abspath(source_path))
        if lexical_path != expected_path:
            raise ValueError(f"{role} must use exact approved path {expected_path}")
        try:
            resolved_path = source_path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"{role} source path cannot be resolved safely") from error
        if resolved_path != expected_path:
            raise ValueError(
                f"{role} resolved path must match exact approved path {expected_path}"
            )
        content = source_path.read_bytes()
        after = source_path.lstat()
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        if after_identity != before_identity:
            raise ValueError(f"{role} source changed while being snapshotted")
        actual_checksum = hashlib.sha256(content).hexdigest()
        if actual_checksum != expected_checksum:
            raise ValueError(f"{role} checksum does not match the approved source")
        snapshots[role] = _SourceSnapshot(
            role=role,
            filename=expected_filename,
            content=content,
            checksum=actual_checksum,
        )
    return snapshots


def _load_evidence_snapshot(snapshot: _SourceSnapshot) -> EvidenceBaseline:
    label = _snapshot_label(snapshot)
    try:
        payload = yaml.load(
            snapshot.content.decode("utf-8"),
            Loader=_UniqueKeySafeLoader,
        )
        return EvidenceBaseline.model_validate(payload)
    except (UnicodeDecodeError, ValidationError, yaml.YAMLError) as error:
        raise ValueError(f"{label}: evidence YAML validation failed") from error


def _load_registry_snapshot(
    snapshot: _SourceSnapshot,
    model_type: type[_RegistryFileModel],
) -> _RegistryFileModel:
    label = _snapshot_label(snapshot)
    try:
        payload = yaml.safe_load(snapshot.content.decode("utf-8"))
        return model_type.model_validate(payload)
    except (UnicodeDecodeError, ValidationError, yaml.YAMLError) as error:
        raise RegistryLoadError(f"{label}: registry YAML validation failed") from error


def _load_registry_snapshots(
    snapshots: dict[str, _SourceSnapshot],
) -> RegistryBundle:
    cycles = _load_registry_snapshot(
        snapshots["cycle_registry"],
        CycleRegistry,
    ).cycles
    indicators = _load_registry_snapshot(
        snapshots["indicator_registry"],
        IndicatorRegistry,
    ).indicators
    channels = _load_registry_snapshot(
        snapshots["channel_registry"],
        ChannelRegistry,
    ).channels
    assets = _load_registry_snapshot(
        snapshots["asset_registry"],
        AssetRegistry,
    ).assets

    try:
        _validate_cycles(cycles)
        cycle_ids = {cycle.cycle_id for cycle in cycles}
        _validate_indicators(indicators, cycle_ids)
        _validate_channels(channels, indicators)
        _validate_assets(assets)
    except ValueError as error:
        labels = ", ".join(
            _snapshot_label(snapshots[role])
            for role in (
                "cycle_registry",
                "indicator_registry",
                "channel_registry",
                "asset_registry",
            )
        )
        raise RegistryLoadError(
            f"registry snapshot cross-validation failed for {labels}"
        ) from error
    return RegistryBundle(
        cycles=cycles,
        indicators=indicators,
        channels=channels,
        assets=assets,
    )


def _require_generated_date(
    payload: dict[str, Any],
    *,
    snapshot: _SourceSnapshot,
) -> None:
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("generated") != "2026-07-19":
        raise ValueError(
            f"{_snapshot_label(snapshot)}: expected generated date 2026-07-19"
        )


def _phase_rows(historical: dict[str, Any]) -> pd.DataFrame:
    c4_payload = historical.get("C4")
    if not isinstance(c4_payload, dict):
        raise ValueError("historical prototype must contain a C4 object")
    cycle_rows = c4_payload.get("cycle")
    if not isinstance(cycle_rows, list) or not cycle_rows:
        raise ValueError("historical prototype C4 cycle must be a non-empty list")
    if any(not isinstance(row, dict) for row in cycle_rows):
        raise ValueError("historical prototype C4 cycle rows must be objects")

    levels = pd.Series(
        [row["factor"] for row in cycle_rows],
        dtype="float64",
    )
    slopes = levels.diff().fillna(0.0)
    phases = []
    for level, slope in zip(levels, slopes, strict=True):
        phase = phase_from_level_slope(level, slope)
        if phase is None:
            raise ValueError("historical C4 level and slope must be finite")
        phases.append(phase.value)

    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                [row["date"] for row in cycle_rows],
                errors="raise",
            )
            + pd.offsets.MonthEnd(0),
            "cycle_id": "C4",
            "vintage": VintageKind.LATEST_HISTORICAL.value,
            "vintage_caveat": _VINTAGE_CAVEAT,
            "angle": [row["phase_angle"] for row in cycle_rows],
            "phase": phases,
            "level": levels,
            "slope": slopes,
            "amplitude": [row["amplitude"] for row in cycle_rows],
            "uncertainty": [abs(row["high"] - row["low"]) / 2 for row in cycle_rows],
            "center_period": 42.0,
            "bandwidth": 2.2,
            "confidence": [row["method_concentration"] for row in cycle_rows],
        }
    )


def _write_phase_rows(
    run_dir: Path,
    phase_rows: pd.DataFrame,
    *,
    context: RunContext,
) -> Path:
    if phase_rows.duplicated(["date", "cycle_id", "vintage"]).any():
        raise ValueError("C4 historical phase dimensions must be unique")
    if not phase_rows["date"].is_monotonic_increasing:
        raise ValueError("C4 historical phase dates must be ordered")
    if set(phase_rows["cycle_id"]) != {"C4"}:
        raise ValueError("research foundation phase rows must contain only C4")

    records = []
    for row in phase_rows.to_dict(orient="records"):
        records.append(
            {
                **row,
                "date": row["date"].date(),
                "run_id": context.run_id,
                "as_of": context.as_of,
                "data_vintage": context.data_vintage,
                "model_version": context.model_version,
                "config_hash": context.config_hash,
                "created_at": context.created_at,
            }
        )
    table = pa.Table.from_pylist(records, schema=CYCLE_PHASE_VINTAGE_SCHEMA)
    product_path = run_dir / CYCLE_PHASE_VINTAGE_FILENAME
    try:
        with product_path.open("xb") as product_file:
            pq.write_table(
                table,
                product_file,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                version="2.6",
                data_page_version="1.0",
            )
        if pq.read_schema(product_path) != CYCLE_PHASE_VINTAGE_SCHEMA:
            raise ValueError("persisted research foundation phase schema mismatch")
    except BaseException:
        product_path.unlink(missing_ok=True)
        raise
    return product_path


def _month_end(value: object, *, name: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty month string")
    try:
        timestamp = pd.Timestamp(value) + pd.offsets.MonthEnd(0)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a valid month") from error
    return timestamp.date()


def _build_asset_identity(
    asset: dict[str, Any],
    *,
    asset_filename: str,
    retrieval_time: datetime,
) -> DataIdentity:
    meta = asset.get("meta")
    summary = asset.get("summary")
    assets = asset.get("assets")
    if not isinstance(meta, dict):
        raise ValueError("asset prototype must contain a meta object")
    if meta.get("cycle") != "C4 inventory cycle":
        raise ValueError("asset prototype must identify the C4 inventory cycle")
    for field_name in ("return_source", "missing_rule"):
        if not isinstance(meta.get(field_name), str) or not meta[field_name]:
            raise ValueError(f"asset prototype meta.{field_name} must be non-empty")
    if not isinstance(summary, dict):
        raise ValueError("asset prototype must contain a summary object")
    if not isinstance(assets, list) or not assets:
        raise ValueError("asset prototype assets must be a non-empty list")
    if any(not isinstance(record, dict) for record in assets):
        raise ValueError("asset prototype asset rows must be objects")

    direct_rows = [
        record for record in assets if record.get("data_identity") == "direct"
    ]
    if not direct_rows:
        raise ValueError("asset prototype contains no direct asset rows")
    unavailable_rows = [
        record
        for record in assets
        if record.get("data_identity") == "configured_source_unavailable"
    ]
    if len(direct_rows) + len(unavailable_rows) != len(assets):
        raise ValueError("asset prototype contains an unknown data identity")
    expected_counts = {
        "total_rows": len(assets),
        "observed_assets": len(direct_rows),
        "unavailable_assets": len(unavailable_rows),
    }
    for field_name, expected_count in expected_counts.items():
        if summary.get(field_name) != expected_count:
            raise ValueError(f"asset prototype summary.{field_name} is inconsistent")

    starts = [
        _month_end(record.get("start"), name="asset start") for record in direct_rows
    ]
    ends = [_month_end(record.get("end"), name="asset end") for record in direct_rows]
    if any(start > end for start, end in zip(starts, ends, strict=True)):
        raise ValueError("asset prototype contains an invalid coverage interval")
    unavailable_assets = {record.get("asset_id") for record in unavailable_rows}
    expected_unavailable = {"商品||黄金", "商品||铜", "商品||原油"}
    if unavailable_assets != expected_unavailable:
        raise ValueError("asset prototype unavailable source set is inconsistent")

    unavailable_labels = {
        "商品||黄金": "Gold",
        "商品||铜": "copper",
        "商品||原油": "crude oil",
    }
    caveat = (
        f"{unavailable_labels['商品||黄金']}, {unavailable_labels['商品||铜']} and "
        f"{unavailable_labels['商品||原油']} direct sources are unavailable."
    )
    return DataIdentity.from_dates(
        entity_id="c4_asset_return_panel",
        source=f"output/{asset_filename}",
        frequency="M",
        unit="monthly_return",
        transform="observed_return",
        observation_start=min(starts),
        data_as_of=max(ends),
        release_date=_APPROVED_AS_OF,
        retrieval_time=retrieval_time,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
        stale_after_months=2,
        proxy_for=None,
        caveat=caveat,
    )


def _asset_identity(
    asset: dict[str, Any],
    *,
    snapshot: _SourceSnapshot,
    retrieval_time: datetime,
) -> DataIdentity:
    try:
        return _build_asset_identity(
            asset,
            asset_filename=snapshot.filename,
            retrieval_time=retrieval_time,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{_snapshot_label(snapshot)}: invalid asset prototype content: {error}"
        ) from error


def _identity_records(
    realtime: dict[str, Any],
    asset: dict[str, Any],
    *,
    historical_snapshot: _SourceSnapshot,
    realtime_snapshot: _SourceSnapshot,
    asset_snapshot: _SourceSnapshot,
    retrieval_time: datetime,
) -> tuple[list[DataIdentity], list[dict[str, object]]]:
    realtime_meta = realtime.get("meta")
    if not isinstance(realtime_meta, dict):
        raise ValueError(
            f"{_snapshot_label(realtime_snapshot)}: realtime prototype must "
            "contain a meta object"
        )
    data_vintage_limit = realtime_meta.get("data_vintage_limit")
    if not isinstance(data_vintage_limit, str) or not data_vintage_limit:
        raise ValueError(
            f"{_snapshot_label(realtime_snapshot)}: realtime prototype must "
            "state its data vintage limit"
        )

    identities = [
        DataIdentity.from_dates(
            entity_id="c4_historical_panel",
            source=f"output/{historical_snapshot.filename}",
            frequency="M",
            unit="standardized_factor",
            transform="family_balanced_two_sided_filter",
            observation_start=date(2005, 1, 31),
            data_as_of=_DATA_VINTAGE,
            release_date=_APPROVED_AS_OF,
            retrieval_time=retrieval_time,
            vintage_kind=VintageKind.LATEST_HISTORICAL,
            stale_after_months=12,
            proxy_for=None,
            caveat=(
                "Historical two-sided result; endpoint is not publishable "
                "realtime state."
            ),
        ),
        DataIdentity.from_dates(
            entity_id="c4_realtime_panel",
            source=f"output/{realtime_snapshot.filename}",
            frequency="M",
            unit="standardized_factor",
            transform="one_sided_harmonic_kalman",
            observation_start=date(2005, 1, 31),
            data_as_of=_DATA_VINTAGE,
            release_date=_APPROVED_AS_OF,
            retrieval_time=retrieval_time,
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            stale_after_months=2,
            proxy_for=None,
            caveat=data_vintage_limit,
        ),
        _asset_identity(
            asset,
            snapshot=asset_snapshot,
            retrieval_time=retrieval_time,
        ),
    ]
    records = [
        {
            "entity_id": identity.entity_id,
            "source": identity.source,
            "frequency": identity.frequency,
            "unit": identity.unit,
            "transform": identity.transform,
            "observation_start": identity.observation_start,
            "source_data_as_of": identity.data_as_of,
            "release_date": identity.release_date,
            "retrieval_time": identity.retrieval_time,
            "vintage_kind": identity.vintage_kind.value,
            "stale_months": identity.stale_months,
            "stale_after_months": identity.stale_after_months,
            "freshness_status": identity.freshness_status.value,
            "proxy_for": identity.proxy_for,
            "caveat": identity.caveat,
        }
        for identity in identities
    ]
    return identities, records


def _calibration_records() -> list[dict[str, object]]:
    return [
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C1",
            "version": "v3",
            "change_summary": (
                "Use family-balanced composites instead of GDP-led aggregation."
            ),
            "impact_summary": (
                "Retain 600-month prior and publish 510-708 month band."
            ),
            "status": "scenario_only",
        },
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C2/C3",
            "version": "v2",
            "change_summary": ("Add raw, log and growth transformation sensitivity."),
            "impact_summary": "Withdraw empirical centers.",
            "status": "blocked",
        },
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C4",
            "version": "v4",
            "change_summary": (
                "Add production, inventory, prices and trade validation."
            ),
            "impact_summary": "Publish 40.0-42.2 month empirical band.",
            "status": "formal",
        },
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C5/C7",
            "version": "v2",
            "change_summary": "Add red-noise and search-boundary audit.",
            "impact_summary": "Downgrade to blocked conditional priors.",
            "status": "blocked",
        },
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C4-realtime",
            "version": "v1",
            "change_summary": (
                "Separate two-sided history from one-sided realtime state."
            ),
            "impact_summary": "Label current validation pseudo-realtime.",
            "status": "limited",
        },
        {
            "calibration_date": _APPROVED_AS_OF,
            "subject_id": "C4-forecast",
            "version": "v1",
            "change_summary": (
                "Evaluate persistence, harmonic, ridge and analog models."
            ),
            "impact_summary": (
                "Only ridge qualifies; stale input prevents formal release."
            ),
            "status": "limited",
        },
    ]


def build_research_foundation(
    *,
    sources: FoundationSources,
    product_root: Path,
    as_of: date,
) -> FoundationBuildResult:
    """Build and atomically publish the approved research foundation products."""

    if not isinstance(sources, FoundationSources):
        raise TypeError("sources must be FoundationSources")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise TypeError("as_of must be a date without time")
    if as_of != _APPROVED_AS_OF:
        raise ValueError("research foundation as_of must be 2026-07-19")

    snapshots = _snapshot_approved_sources(sources)
    input_checksums = {
        snapshot.filename: snapshot.checksum for snapshot in snapshots.values()
    }
    baseline = _load_evidence_snapshot(snapshots["evidence_baseline"])
    registry = _load_registry_snapshots(snapshots)
    historical_snapshot = snapshots["historical_prototype"]
    realtime_snapshot = snapshots["realtime_prototype"]
    forecast_snapshot = snapshots["forecast_prototype"]
    asset_snapshot = snapshots["asset_prototype"]
    historical = _load_json(historical_snapshot)
    realtime = _load_json(realtime_snapshot)
    forecast = _load_json(forecast_snapshot)
    asset = _load_json(asset_snapshot)
    _require_generated_date(historical, snapshot=historical_snapshot)
    _require_generated_date(realtime, snapshot=realtime_snapshot)
    _require_generated_date(forecast, snapshot=forecast_snapshot)
    _require_generated_date(asset, snapshot=asset_snapshot)

    retrieval_time = datetime.combine(as_of, time.min, tzinfo=timezone.utc)
    try:
        phase_rows = _phase_rows(historical)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{_snapshot_label(historical_snapshot)}: invalid historical "
            f"prototype content: {error}"
        ) from error
    identities, identity_records = _identity_records(
        realtime,
        asset,
        historical_snapshot=historical_snapshot,
        realtime_snapshot=realtime_snapshot,
        asset_snapshot=asset_snapshot,
        retrieval_time=retrieval_time,
    )
    identity_lookup = {identity.entity_id: identity for identity in identities}
    historical_identity = identity_lookup["c4_historical_panel"]
    realtime_identity = identity_lookup["c4_realtime_panel"]
    asset_identity = identity_lookup["c4_asset_return_panel"]
    identity_by_layer = {
        "historical": historical_identity,
        "realtime": realtime_identity,
        "forecast": realtime_identity,
        "asset_statistics": asset_identity,
    }

    evidence_records = [
        {
            "cycle_id": record.cycle_id,
            "evidence_status": record.evidence_status,
            "center_prior_months": record.center_prior_months,
            "empirical_min_months": (
                record.empirical_band_months[0]
                if record.empirical_band_months is not None
                else None
            ),
            "empirical_max_months": (
                record.empirical_band_months[1]
                if record.empirical_band_months is not None
                else None
            ),
            "family_centers_json": _canonical_json(record.family_centers_months),
            "reason_codes_json": _canonical_json(record.reason_codes),
            "summary": record.summary,
        }
        for record in baseline.cycles
    ]
    evidence_lookup = {record.cycle_id: record for record in baseline.cycles}
    qualified_models = forecast.get("qualified_models")
    if not isinstance(qualified_models, list) or any(
        not isinstance(model, str) for model in qualified_models
    ):
        raise ValueError(
            f"{_snapshot_label(forecast_snapshot)}: forecast prototype "
            "qualified_models must be a string list"
        )

    gate_records = []
    for cycle in registry.cycles:
        evidence = evidence_lookup[cycle.cycle_id]
        for layer in _RESEARCH_LAYERS:
            identity = identity_by_layer[layer]
            configured_status = getattr(cycle.publication, layer)
            model_qualified = None
            if (
                layer == "forecast"
                and configured_status is not PublicationGateStatus.CALENDAR_ONLY
            ):
                model_qualified = cycle.cycle_id == "C4" and qualified_models == [
                    "ridge"
                ]
            decision = evaluate_gate(
                GateInput(
                    cycle_id=cycle.cycle_id,
                    layer=layer,
                    configured_status=configured_status,
                    evidence_status=evidence.evidence_status,
                    vintage_kind=identity.vintage_kind,
                    freshness=identity.freshness_status,
                    model_qualified=model_qualified,
                )
            )
            gate_records.append(
                {
                    "cycle_id": decision.cycle_id,
                    "layer": decision.layer,
                    "status": decision.status.value,
                    "reason_codes_json": _canonical_json(decision.reason_codes),
                }
            )

    context = RunContext.create(
        as_of=as_of,
        data_vintage=_DATA_VINTAGE,
        model_version="research-foundation-v1",
        config={
            "pipeline": "research_foundation",
            "evidence_generated": baseline.generated.isoformat(),
        },
        input_checksums=input_checksums,
        quality_summary={
            "cycle_evidence_records": 7,
            "formal_historical_cycles": 1,
            "pseudo_realtime": 1,
            "stale_sources": 2,
        },
        created_at=retrieval_time,
    )

    def write_staging(staging_dir: Path) -> None:
        _write_phase_rows(staging_dir, phase_rows, context=context)
        write_records(
            staging_dir,
            filename=CYCLE_EVIDENCE_FILENAME,
            schema=CYCLE_EVIDENCE_SCHEMA,
            records=evidence_records,
            context=context,
        )
        write_records(
            staging_dir,
            filename=DATA_IDENTITY_FILENAME,
            schema=DATA_IDENTITY_SCHEMA,
            records=identity_records,
            context=context,
        )
        write_records(
            staging_dir,
            filename=PUBLICATION_GATE_FILENAME,
            schema=PUBLICATION_GATE_SCHEMA,
            records=gate_records,
            context=context,
        )
        write_records(
            staging_dir,
            filename=CALIBRATION_LOG_FILENAME,
            schema=CALIBRATION_LOG_SCHEMA,
            records=_calibration_records(),
            context=context,
        )

    manifest = publish_run(
        Path(product_root),
        context,
        write_staging=write_staging,
    )
    return FoundationBuildResult(
        run_id=manifest.run_id,
        run_dir=Path(product_root) / "runs" / manifest.run_id,
    )


__all__ = [
    "FoundationBuildResult",
    "FoundationSources",
    "build_research_foundation",
]
