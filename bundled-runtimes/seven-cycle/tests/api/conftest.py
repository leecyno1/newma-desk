"""Published-run fixtures for API contract tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from fastapi.testclient import TestClient
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.api.app import create_app
from seven_cycle_platform.catalog import build_catalog, open_catalog
from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_SCHEMA,
    CYCLE_PHASE_VINTAGE_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_SCHEMA,
)
from seven_cycle_platform.products.cycle_forecast import CYCLE_FORECAST_SCHEMA
from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_SCHEMA,
)
from seven_cycle_platform.storage import RunContext, publish_run


HISTORICAL_ANALOG_SCHEMA = pa.schema(
    [
        pa.field("historical_date", pa.date32()),
        pa.field("historical_vintage", pa.date32()),
        pa.field("analog_rank", pa.int32()),
        pa.field("distance", pa.float64()),
        pa.field("effective_samples", pa.int32()),
        pa.field("cycle_difference_json", pa.string()),
        pa.field("channel_difference_json", pa.string()),
        pa.field("asset_outcome_json", pa.string()),
        pa.field("status", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass(frozen=True)
class PublishedRun:
    context: RunContext
    manifest: object
    product_root: Path
    catalog_root: Path

    @property
    def run_dir(self) -> Path:
        return self.product_root / "runs" / self.context.run_id

    @property
    def catalog_path(self) -> Path:
        return self.catalog_root / f"{self.context.run_id}.duckdb"


CatalogFileIdentity = tuple[int, int]


def _regular_file_identity(path: Path) -> CatalogFileIdentity | None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(path_stat.st_mode):
        return None
    return path_stat.st_dev, path_stat.st_ino


def _cleanup_owned_catalog(
    path: Path,
    expected_identity: CatalogFileIdentity | None,
) -> str | None:
    """Best-effort cleanup that never removes a replacement catalog object."""

    if expected_identity is None:
        return None
    try:
        actual_identity = _regular_file_identity(path)
    except OSError as error:
        return f"could not inspect candidate catalog cleanup target: {error}"
    if actual_identity != expected_identity:
        return None
    try:
        path.unlink()
    except OSError as error:
        return f"could not remove owned candidate catalog: {error}"
    return None


def _add_cleanup_notes(error: BaseException, notes: list[str]) -> None:
    for note in notes:
        error.add_note(note)


def _table(schema: pa.Schema, values: dict[str, list[object]]) -> pa.Table:
    row_count = len(next(iter(values.values())))
    return pa.Table.from_arrays(
        [
            pa.array(
                values.get(field.name, [None] * row_count),
                type=field.type,
                from_pandas=True,
            )
            for field in schema
        ],
        schema=schema,
    )


def _provenance(context: RunContext, row_count: int) -> dict[str, list[object]]:
    return {
        "run_id": [context.run_id] * row_count,
        "as_of": [context.as_of] * row_count,
        "data_vintage": [context.data_vintage] * row_count,
        "model_version": [context.model_version] * row_count,
        "config_hash": [context.config_hash] * row_count,
        "created_at": [context.created_at] * row_count,
    }


def _tables(context: RunContext, *, stale: bool) -> dict[str, pa.Table]:
    cycle_provenance = _provenance(context, 4)
    attribution_provenance = _provenance(context, 3)
    forecast_provenance = _provenance(context, 3)
    future_provenance = _provenance(context, 4)
    current_provenance = _provenance(context, 3)
    analog_provenance = _provenance(context, 2)
    current_provenance.pop("config_hash")
    return {
        "cycle_phase_vintage.parquet": _table(
            CYCLE_PHASE_VINTAGE_SCHEMA,
            {
                "date": [context.as_of] * 4,
                "cycle_id": ["C1", "C1", "C2", "C2"],
                "vintage": [
                    "realtime",
                    "latest_historical",
                    "realtime",
                    "latest_historical",
                ],
                "phase": ["expansion", "expansion", "contraction", "contraction"],
                **cycle_provenance,
            },
        ),
        "cycle_forecast.parquet": _table(
            CYCLE_FORECAST_SCHEMA,
            {
                "cycle_id": ["C1", "C1", "C2"],
                "horizon_months": [3, 12, 12],
                "forecast_date": [context.as_of] * 3,
                "status": ["available", "available", "available"],
                "turning_status": ["available", "available", "available"],
                **forecast_provenance,
            },
        ),
        "asset_attribution.parquet": _table(
            ASSET_ATTRIBUTION_SCHEMA,
            {
                "asset_id": ["asset-valid", "asset-valid", "asset-failed"],
                "horizon_months": [3, 12, 12],
                "period_end": [context.as_of] * 3,
                "status": ["available", "available", "unavailable"],
                "evidence_level": ["formal", "formal", "retrospective_only"],
                **attribution_provenance,
            },
        ),
        "asset_mapping_current.parquet": _table(
            ASSET_MAPPING_CURRENT_SCHEMA,
            {
                "asset_id": ["asset-valid", "asset-valid", "asset-failed"],
                "horizon_months": [3, 12, 12],
                "mapping_status": ["available", "available", "unavailable"],
                "freshness_status": ["fresh", "fresh", "stale" if stale else "fresh"],
                "freshness_reason_codes": [
                    None,
                    None,
                    "SOURCE_STALE" if stale else None,
                ],
                "publication_status": ["live", "live", "partial"],
                "publication_reason_codes": [None, None, "ASSET_SOURCE_FAILED"],
                "evidence_level": ["formal", "formal", "retrospective_only"],
                **current_provenance,
            },
        ),
        "asset_mapping_future.parquet": _table(
            ASSET_MAPPING_FUTURE_SCHEMA,
            {
                "scenario_id": ["baseline", "baseline", "stress", "baseline"],
                "asset_id": [
                    "asset-valid",
                    "asset-valid",
                    "asset-valid",
                    "asset-failed",
                ],
                "horizon_months": [3, 12, 12, 12],
                "future_date": [context.as_of] * 4,
                "status": ["available", "available", "available", "unavailable"],
                "mapping_status": [
                    "available",
                    "available",
                    "available",
                    "unavailable",
                ],
                "mapping_status_reason_codes": [
                    None,
                    None,
                    None,
                    "ASSET_SOURCE_FAILED",
                ],
                "freshness_status": [
                    "fresh",
                    "fresh",
                    "fresh",
                    "stale" if stale else "fresh",
                ],
                "freshness_reason_codes": [
                    None,
                    None,
                    None,
                    "SOURCE_STALE" if stale else None,
                ],
                "scenario_version": ["scenario-v1"] * 4,
                "catalog_version": ["catalog-v1"] * 4,
                "scenario_config_hash": [hashlib.sha256(b"scenario").hexdigest()] * 4,
                **future_provenance,
            },
        ),
        "historical_analogs.parquet": _table(
            HISTORICAL_ANALOG_SCHEMA,
            {
                "historical_date": [date(2025, 1, 31), date(2025, 2, 28)],
                "historical_vintage": [date(2025, 2, 1), date(2025, 3, 1)],
                "analog_rank": [2, 1],
                "distance": [0.2, 0.1],
                "effective_samples": [100, 100],
                "cycle_difference_json": ["{}", "{}"],
                "channel_difference_json": ["{}", "{}"],
                "asset_outcome_json": ["{}", "{}"],
                "status": ["available", "available"],
                **analog_provenance,
            },
        ),
        "cycle_evidence.parquet": _table(
            CYCLE_EVIDENCE_SCHEMA,
            {
                "cycle_id": ["C4", "C5"],
                "evidence_status": ["supported", "unidentified"],
                "center_prior_months": [42.0, 20.0],
                "empirical_min_months": [40.0, None],
                "empirical_max_months": [42.2, None],
                "family_centers_json": ["[40.0,42.2]", "[]"],
                "reason_codes_json": [
                    '["cross_family_consensus"]',
                    '["red_noise_not_significant"]',
                ],
                "summary": ["C4 supported.", "C5 unidentified."],
                **_provenance(context, 2),
            },
        ),
        "publication_gate.parquet": _table(
            PUBLICATION_GATE_SCHEMA,
            {
                "cycle_id": ["C4", "C5", "C5", "C5", "C5"],
                "layer": [
                    "historical",
                    "historical",
                    "realtime",
                    "forecast",
                    "asset_statistics",
                ],
                "status": ["formal", "blocked", "blocked", "blocked", "blocked"],
                "reason_codes_json": [
                    '["configured_policy"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                ],
                **_provenance(context, 5),
            },
        ),
        "data_identity.parquet": _table(
            DATA_IDENTITY_SCHEMA,
            {
                "entity_id": ["c4_macro_panel"],
                "source": ["approved_prototype"],
                "frequency": ["M"],
                "unit": ["standardized_factor"],
                "transform": ["family_balanced_composite"],
                "observation_start": [date(2005, 1, 31)],
                "source_data_as_of": [date(2025, 12, 31)],
                "release_date": [date(2026, 7, 19)],
                "retrieval_time": [datetime(2026, 7, 19, tzinfo=timezone.utc)],
                "vintage_kind": ["pseudo_vintage"],
                "stale_months": [7],
                "stale_after_months": [2],
                "freshness_status": ["stale"],
                "proxy_for": [None],
                "caveat": ["Original release vintages unavailable."],
                **_provenance(context, 1),
            },
        ),
        "calibration_log.parquet": _table(
            CALIBRATION_LOG_SCHEMA,
            {
                "calibration_date": [date(2026, 7, 19)],
                "subject_id": ["C4"],
                "version": ["v4"],
                "change_summary": ["Added four-family validation."],
                "impact_summary": ["Empirical band 40.0-42.2 months."],
                "status": ["formal"],
                **_provenance(context, 1),
            },
        ),
    }


def publish_catalog(
    product_root: Path,
    catalog_root: Path,
    *,
    label: str,
    stale: bool = False,
    validate_published: Callable[[Path, object], None] | None = None,
    after_catalog_before_latest: Callable[[PublishedRun], None] | None = None,
) -> PublishedRun:
    """Publish products only after their catalog validates before latest advances."""

    context = RunContext.create(
        as_of=date(2026, 6, 30) if label == "a" else date(2026, 7, 31),
        data_vintage=date(2026, 6, 30) if label == "a" else date(2026, 7, 31),
        model_version=f"contract-{label}",
        config={"api_contract": label},
        input_checksums={"inputs/source": hashlib.sha256(label.encode()).hexdigest()},
        quality_summary={"checks": {"failed": 1 if stale else 0, "passed": 5}},
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    tables = _tables(context, stale=stale)
    catalog_root.mkdir(parents=True, exist_ok=True)
    catalog_path = catalog_root / f"{context.run_id}.duckdb"
    temporary_catalog: Path | None = None
    temporary_identity: CatalogFileIdentity | None = None
    installed_catalog_identity: CatalogFileIdentity | None = None

    def write_staging(staging_dir: Path) -> None:
        for filename, table in tables.items():
            pq.write_table(table, staging_dir / filename)

    def validate_and_catalog(run_dir: Path, manifest: object) -> None:
        nonlocal installed_catalog_identity, temporary_catalog, temporary_identity
        if validate_published is not None:
            validate_published(run_dir, manifest)
        candidate = PublishedRun(
            context=context,
            manifest=manifest,
            product_root=product_root,
            catalog_root=catalog_root,
        )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=catalog_root,
            prefix=f".{context.run_id}.",
            suffix=".duckdb",
        )
        os.close(descriptor)
        temporary_catalog = Path(temporary_name)
        temporary_identity = _regular_file_identity(temporary_catalog)
        if temporary_identity is None:
            raise RuntimeError("candidate catalog temporary path is not a regular file")
        build_catalog(run_dir, temporary_catalog, expected_manifest=manifest)
        temporary_identity = _regular_file_identity(temporary_catalog)
        if temporary_identity is None:
            raise RuntimeError("candidate catalog build did not produce a regular file")
        connection = open_catalog(
            temporary_catalog,
            run_dir=run_dir,
            expected_manifest=manifest,
        )
        connection.close()
        try:
            os.link(temporary_catalog, catalog_path)
        except FileExistsError as error:
            raise FileExistsError(f"catalog already exists: {catalog_path}") from error
        installed_catalog_identity = _regular_file_identity(catalog_path)
        if installed_catalog_identity != temporary_identity:
            raise RuntimeError("candidate catalog changed during atomic installation")
        cleanup_note = _cleanup_owned_catalog(temporary_catalog, temporary_identity)
        if cleanup_note is not None:
            raise RuntimeError(cleanup_note)
        temporary_catalog = None
        temporary_identity = None
        if after_catalog_before_latest is not None:
            after_catalog_before_latest(candidate)

    try:
        manifest = publish_run(
            product_root,
            context,
            write_staging=write_staging,
            validate_published=validate_and_catalog,
        )
    except BaseException as error:
        cleanup_notes = [
            note
            for note in (
                _cleanup_owned_catalog(catalog_path, installed_catalog_identity),
                _cleanup_owned_catalog(temporary_catalog, temporary_identity)
                if temporary_catalog is not None
                else None,
            )
            if note is not None
        ]
        _add_cleanup_notes(error, cleanup_notes)
        raise
    return PublishedRun(
        context=context,
        manifest=manifest,
        product_root=product_root,
        catalog_root=catalog_root,
    )


def assert_row_provenance(response: object, published_run: PublishedRun) -> None:
    body = response.json()
    expected = {
        "run_id": published_run.context.run_id,
        "as_of": published_run.context.as_of.isoformat(),
        "data_vintage": published_run.context.data_vintage.isoformat(),
        "model_version": published_run.context.model_version,
        "config_hash": published_run.context.config_hash,
    }
    assert {key: body["provenance"][key] for key in expected} == expected
    for row in body["data"]:
        assert {key: row[key] for key in expected} == expected


@pytest.fixture
def published_run(tmp_path: Path) -> PublishedRun:
    return publish_catalog(
        tmp_path / "products",
        tmp_path / "catalogs",
        label="a",
        stale=True,
    )


@pytest.fixture
def client(published_run: PublishedRun) -> TestClient:
    with TestClient(
        create_app(
            product_root=published_run.product_root,
            catalog_root=published_run.catalog_root,
        )
    ) as test_client:
        yield test_client
