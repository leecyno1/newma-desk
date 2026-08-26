from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import seven_cycle_platform.catalog.duckdb as catalog_api
from seven_cycle_platform.catalog import (
    CATALOG_SCHEMA_VERSION,
    STABLE_VIEW_NAMES,
    CatalogBuildError,
    CatalogRepairRefusedError,
    CatalogVerificationError,
    build_catalog,
    open_catalog,
    repair_catalog_device_identity_drift,
)
from seven_cycle_platform.contracts.arrow import (
    ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
    ASSET_ATTRIBUTION_SCHEMA,
    CHANNEL_STATE_SCHEMA,
    CYCLE_PHASE_VINTAGE_SCHEMA,
    QUALITY_FINDING_SCHEMA,
)
from seven_cycle_platform.pipeline.research_foundation import (
    FoundationSources,
    build_research_foundation,
)
from seven_cycle_platform.products.asset_mapping_current import (
    ASSET_MAPPING_CURRENT_SCHEMA,
)
from seven_cycle_platform.products.asset_mapping_future import (
    ASSET_MAPPING_FUTURE_SCHEMA,
)
from seven_cycle_platform.products.cycle_forecast import CYCLE_FORECAST_SCHEMA
from seven_cycle_platform.products.cycle_asset_surface import CYCLE_ASSET_SURFACE_SCHEMA
from seven_cycle_platform.products.research_governance import (
    CALIBRATION_LOG_FILENAME,
    CALIBRATION_LOG_SCHEMA,
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    DATA_IDENTITY_FILENAME,
    DATA_IDENTITY_SCHEMA,
    PUBLICATION_GATE_FILENAME,
    PUBLICATION_GATE_SCHEMA,
)
from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import (
    ManifestVerificationError,
    load_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _PublishedFixture:
    product_root: Path
    run_dir: Path
    manifest: object


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context(*, quality_summary: dict[str, object] | None = None) -> RunContext:
    return RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="catalog-fixture-v1",
        config={"catalog": "fixture"},
        input_checksums={"inputs/source.parquet": _checksum(b"source")},
        quality_summary=quality_summary or {"checks": {"failed": 0, "passed": 6}},
        created_at=datetime(2026, 7, 15, 1, 2, tzinfo=timezone.utc),
    )


def _table(
    schema: pa.Schema,
    row_count: int,
    values: dict[str, list[object]],
) -> pa.Table:
    arrays = [
        pa.array(
            values.get(field.name, [None] * row_count),
            type=field.type,
            from_pandas=True,
        )
        for field in schema
    ]
    return pa.Table.from_arrays(arrays, schema=schema)


def _replace_column(
    table: pa.Table,
    column_name: str,
    values: list[object],
) -> pa.Table:
    index = table.schema.get_field_index(column_name)
    field = table.schema.field(index)
    return table.set_column(
        index,
        field,
        pa.array(values, type=field.type, from_pandas=True),
    )


def _malformed_schema_table(
    schema: pa.Schema,
    malformation: str,
) -> pa.Table:
    table = _table(schema, 0, {})
    if malformation == "missing":
        return table.select(schema.names[1:])
    if malformation == "type":
        fields = list(schema)
        fields[0] = pa.field(fields[0].name, pa.int64(), nullable=fields[0].nullable)
        arrays = list(table.columns)
        arrays[0] = pa.chunked_array([pa.array([], type=pa.int64())])
        return pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    names = list(schema.names)
    names[0], names[1] = names[1], names[0]
    return table.select(names)


def _core_tables(context: RunContext) -> dict[str, pa.Table]:
    cycle_dates = [
        date(2026, 5, 31),
        date(2026, 5, 31),
        date(2026, 6, 30),
        date(2026, 6, 30),
        date(2026, 6, 30),
        date(2026, 6, 30),
    ]
    return {
        "cycle_phase_vintage.parquet": _table(
            CYCLE_PHASE_VINTAGE_SCHEMA,
            6,
            {
                "date": cycle_dates,
                "cycle_id": ["C1", "C2", "C1", "C2", "C1", "C2"],
                "vintage": [
                    "realtime",
                    "realtime",
                    "realtime",
                    "realtime",
                    "latest_historical",
                    "latest_historical",
                ],
                "run_id": [context.run_id] * 6,
                "as_of": [context.as_of] * 6,
                "data_vintage": [context.data_vintage] * 6,
                "model_version": [context.model_version] * 6,
                "config_hash": [context.config_hash] * 6,
                "created_at": [context.created_at] * 6,
            },
        ),
        "channel_state.parquet": _table(
            CHANNEL_STATE_SCHEMA,
            2,
            {
                "channel_id": ["growth", "inflation"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of] * 2,
                "data_vintage": [context.data_vintage] * 2,
                "model_version": [context.model_version] * 2,
                "config_hash": [context.config_hash] * 2,
                "created_at": [context.created_at] * 2,
            },
        ),
        "asset_attribution.parquet": _table(
            ASSET_ATTRIBUTION_SCHEMA,
            2,
            {
                "asset_id": ["asset-a", "asset-b"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of] * 2,
                "data_vintage": [context.data_vintage] * 2,
                "model_version": [context.model_version] * 2,
                "config_hash": [context.config_hash] * 2,
                "created_at": [context.created_at] * 2,
            },
        ),
        "asset_attribution_conservation.parquet": _table(
            ASSET_ATTRIBUTION_CONSERVATION_SCHEMA,
            1,
            {
                "asset_id": ["asset-a"],
                "period_end": [context.as_of],
                "point_conservation_error": [0.0],
                "status": ["passed"],
                "run_id": [context.run_id],
                "as_of": [context.as_of],
                "data_vintage": [context.data_vintage],
                "model_version": [context.model_version],
                "config_hash": [context.config_hash],
                "created_at": [context.created_at],
            },
        ),
        "asset_mapping_current.parquet": _table(
            ASSET_MAPPING_CURRENT_SCHEMA,
            2,
            {
                "asset_id": ["asset-a", "asset-b"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of] * 2,
                "data_vintage": [context.data_vintage] * 2,
                "model_version": [context.model_version] * 2,
                "created_at": [context.created_at] * 2,
            },
        ),
        "cycle_forecast.parquet": _table(
            CYCLE_FORECAST_SCHEMA,
            2,
            {
                "cycle_id": ["C1", "C2"],
                "run_id": [context.run_id, context.run_id],
                "as_of": [context.as_of] * 2,
                "data_vintage": [context.data_vintage] * 2,
                "model_version": [context.model_version] * 2,
                "config_hash": [context.config_hash] * 2,
                "created_at": [context.created_at] * 2,
            },
        ),
        "asset_mapping_future.parquet": _table(
            ASSET_MAPPING_FUTURE_SCHEMA,
            3,
            {
                "scenario_id": ["baseline", "growth", "baseline"],
                "asset_id": ["asset-a", "asset-a", "asset-b"],
                "scenario_version": ["scenario-v1"] * 3,
                "catalog_version": ["catalog-v1"] * 3,
                "scenario_config_hash": [_checksum(b"scenario")] * 3,
                "run_id": [context.run_id] * 3,
                "as_of": [context.as_of] * 3,
                "data_vintage": [context.data_vintage] * 3,
                "model_version": [context.model_version] * 3,
                "config_hash": [context.config_hash] * 3,
                "created_at": [context.created_at] * 3,
            },
        ),
        "quality_findings.parquet": _table(
            QUALITY_FINDING_SCHEMA,
            1,
            {
                "entity_id": ["catalog-fixture"],
                "check": ["schema_contract"],
                "severity": ["info"],
                "status": ["passed"],
                "message": ["fixture is valid"],
                "observed_value": [1.0],
                "threshold": [1.0],
            },
        ),
    }


def _published_run(
    tmp_path: Path,
    *,
    include_products: set[str] | None = None,
    relative_parent: str | None = None,
    quality_summary: dict[str, object] | None = None,
    wrong_run_product: str | None = None,
    table_overrides: dict[str, pa.Table] | None = None,
    provenance_override: tuple[str, str, object] | None = None,
    include_surface: bool = False,
) -> _PublishedFixture:
    context = _context(quality_summary=quality_summary)
    product_root = tmp_path / "products"
    tables = _core_tables(context)
    if include_surface:
        tables["cycle_asset_surface.parquet"] = _table(
            CYCLE_ASSET_SURFACE_SCHEMA,
            1,
            {
                "asset_id": ["asset-surface"],
                "asset_label": ["资产A"],
                "cycle_x": ["C1"],
                "cycle_y": ["C2"],
                "metric": ["observed_return"],
                "horizon_months": [12],
                "scenario_id": ["baseline"],
                "window_months": [60],
                "grid_size": [19],
                "status": ["not_identifiable"],
                "estimator_version": ["circular-kernel-loocv-v1"],
                "sample_count": [0],
                "identifiable": [False],
                "reason": ["样本不足"],
                "observations_json": ["[]"],
                "grid_json": ["[]"],
                "future_path_json": ["[]"],
                "run_id": [context.run_id],
                "as_of": [context.as_of],
                "data_vintage": [context.data_vintage],
                "model_version": [context.model_version],
                "config_hash": [context.config_hash],
                "created_at": [context.created_at],
            },
        )
    if table_overrides is not None:
        tables.update(table_overrides)
    selected = include_products or set(tables)

    def write_staging(staging_dir: Path) -> None:
        output_dir = staging_dir
        if relative_parent is not None:
            output_dir = staging_dir / relative_parent
            output_dir.mkdir(parents=True)
        for filename in sorted(selected):
            table = tables[filename]
            if filename == wrong_run_product:
                table = _replace_column(
                    table,
                    "run_id",
                    ["different-run"] * table.num_rows,
                )
            if provenance_override is not None and filename == provenance_override[0]:
                table = _replace_column(
                    table,
                    provenance_override[1],
                    [provenance_override[2]] * table.num_rows,
                )
            pq.write_table(table, output_dir / filename)

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )
    return _PublishedFixture(
        product_root=product_root,
        run_dir=product_root / "runs" / manifest.run_id,
        manifest=manifest,
    )


def _catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalogs" / "products.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _foundation_sources() -> FoundationSources:
    approved_config = (
        PROJECT_ROOT / "config" / "seven_cycle" / "approved" / "2026-07-19"
    )
    return FoundationSources(
        config_dir=approved_config,
        evidence_path=approved_config / "evidence_baseline.yaml",
        historical_path=(
            PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
        ),
        realtime_path=(
            PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
        ),
        forecast_path=(
            PROJECT_ROOT / "output" / "c4_forecast_prototype_2026-07-19.json"
        ),
        asset_path=(
            PROJECT_ROOT / "output" / "c4_asset_statistics_prototype_2026-07-19.json"
        ),
    )


def _path_state(path: Path) -> tuple[int, int, int, bytes]:
    path_stat = path.lstat()
    return (
        path_stat.st_ino,
        path_stat.st_mtime_ns,
        path_stat.st_size,
        path.read_bytes(),
    )


def _run_state(run_dir: Path) -> dict[str, tuple[int, int, int, bytes]]:
    return {
        path.relative_to(run_dir).as_posix(): _path_state(path)
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }


def test_build_catalog_exposes_all_stable_views_and_single_run_data(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)

    result = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result.path == catalog_path.resolve()
    assert result.run_id == fixture.manifest.run_id
    assert result.view_names == STABLE_VIEW_NAMES
    assert CATALOG_SCHEMA_VERSION == 3
    assert {
        "cycle_evidence",
        "data_identity",
        "publication_gates",
        "calibration_log",
    } <= set(result.view_names)
    assert result.product_count == 8
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert connection.execute(
            "SELECT catalog_schema_version, stable_view_count FROM _catalog_metadata"
        ).fetchone() == (3, len(STABLE_VIEW_NAMES))
        row_counts = {
            view_name: connection.execute(
                f'SELECT count(*) FROM "{view_name}"'
            ).fetchone()[0]
            for view_name in STABLE_VIEW_NAMES
        }
        assert row_counts == {
            "runs": 1,
            "cycle_current": 2,
            "cycle_history": 6,
            "cycle_forecast": 2,
            "assets": 2,
            "attribution": 2,
            "asset_mapping_current": 2,
            "asset_mapping_future": 3,
            "cycle_asset_surface": 0,
            "historical_analogs": 0,
            "scenarios": 2,
            "quality_findings": 4,
            "cycle_evidence": 0,
            "data_identity": 0,
            "publication_gates": 0,
            "calibration_log": 0,
        }
        for view_name in STABLE_VIEW_NAMES:
            columns = {
                row[0]
                for row in connection.execute(f'DESCRIBE "{view_name}"').fetchall()
            }
            assert "run_id" in columns
            assert (
                connection.execute(
                    f'SELECT count(DISTINCT run_id) FROM "{view_name}"'
                ).fetchone()[0]
                <= 1
            )
        current = connection.execute(
            "SELECT cycle_id, date, vintage FROM cycle_current ORDER BY cycle_id"
        ).fetchall()
        assert current == [
            ("C1", date(2026, 6, 30), "realtime"),
            ("C2", date(2026, 6, 30), "realtime"),
        ]
        assert connection.execute(
            "SELECT asset_id FROM assets ORDER BY asset_id"
        ).fetchall() == [("asset-a",), ("asset-b",)]
        assert connection.execute(
            "SELECT scenario_id FROM scenarios ORDER BY scenario_id"
        ).fetchall() == [("baseline",), ("growth",)]


def test_catalog_exposes_foundation_governance_products(tmp_path: Path) -> None:
    foundation = build_research_foundation(
        sources=_foundation_sources(),
        product_root=tmp_path / "foundation-products",
        as_of=date(2026, 7, 19),
    )
    manifest = load_manifest(foundation.run_dir)
    result = build_catalog(
        foundation.run_dir,
        _catalog_path(tmp_path),
        expected_manifest=manifest,
    )

    with open_catalog(
        result.path,
        run_dir=foundation.run_dir,
        expected_manifest=manifest,
    ) as connection:
        evidence = connection.execute(
            "SELECT cycle_id, evidence_status FROM cycle_evidence WHERE cycle_id = 'C4'"
        ).fetchone()
        identity = connection.execute(
            "SELECT entity_id, freshness_status FROM data_identity "
            "WHERE entity_id = 'c4_realtime_panel'"
        ).fetchone()
        gates = connection.execute(
            "SELECT cycle_id, layer, status "
            "FROM publication_gates ORDER BY cycle_id, layer"
        ).fetchall()
        calibration = connection.execute(
            "SELECT subject_id, version, status FROM calibration_log "
            "WHERE subject_id = 'C4'"
        ).fetchone()

    assert evidence == ("C4", "supported")
    assert identity == ("c4_realtime_panel", "stale")
    assert ("C4", "historical", "formal") in gates
    assert ("C5", "asset_statistics", "blocked") in gates
    assert calibration == ("C4", "v4", "formal")


def test_pre_task_7_v2_catalog_is_rejected_by_schema_version(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    with duckdb.connect(str(catalog_path)) as connection:
        connection.execute(
            "UPDATE _catalog_metadata SET catalog_schema_version = 2, "
            "stable_view_count = 12"
        )
        connection.execute("CHECKPOINT")

    with pytest.raises(
        CatalogVerificationError,
        match="catalog schema version mismatch: expected 3, found 2",
    ):
        open_catalog(
            catalog_path,
            run_dir=fixture.run_dir,
            expected_manifest=fixture.manifest,
        )


def test_catalog_metadata_corruption_is_not_a_version_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    with duckdb.connect(str(catalog_path)) as connection:
        connection.execute("UPDATE _catalog_metadata SET stable_view_count = 999")
        connection.execute("CHECKPOINT")

    with pytest.raises(
        CatalogVerificationError,
        match="catalog metadata is corrupt",
    ) as error:
        open_catalog(
            catalog_path,
            run_dir=fixture.run_dir,
            expected_manifest=fixture.manifest,
        )

    assert "version mismatch" not in str(error.value)


def test_catalog_exposes_published_cycle_asset_surface(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path, include_surface=True)
    catalog_path = _catalog_path(tmp_path)

    result = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result.product_count == 9
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        row = connection.execute(
            "SELECT asset_id, cycle_x, cycle_y, status, observations_json, grid_json "
            "FROM cycle_asset_surface"
        ).fetchone()
        assert row == ("asset-surface", "C1", "C2", "not_identifiable", "[]", "[]")
        assert connection.execute(
            "SELECT asset_id FROM assets WHERE asset_id = 'asset-surface'"
        ).fetchall() == [("asset-surface",)]


def test_catalog_contains_only_metadata_tables_and_parquet_source_views(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        base_tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
            ).fetchall()
        }
        assert base_tables == {
            "_catalog_metadata",
            "_catalog_products",
            "_catalog_quality_records",
            "_catalog_quality_summary",
            "_catalog_views",
        }
        source_sql = dict(
            connection.execute(
                "SELECT view_name, sql FROM duckdb_views() "
                "WHERE database_name = current_database() "
                "AND schema_name = 'main' AND view_name LIKE '_src_%'"
            ).fetchall()
        )
        available_sources = {
            row[0]
            for row in connection.execute(
                "SELECT source_view FROM _catalog_products "
                "WHERE available AND source_view IS NOT NULL"
            ).fetchall()
        }
        assert all(
            "read_parquet" in source_sql[source_view]
            for source_view in available_sources
        )
        assert "read_parquet" not in source_sql["_src_historical_analogs"]
        quality_sql = connection.execute(
            "SELECT sql FROM duckdb_views() "
            "WHERE database_name = current_database() "
            "AND schema_name = 'main' AND view_name = 'quality_findings'"
        ).fetchone()[0]
        assert "_catalog_quality" in quality_sql
        assert "read_parquet" not in quality_sql
        assert "_src_" not in quality_sql


def test_cycle_current_selects_latest_visible_row_per_cycle(tmp_path: Path) -> None:
    context = _context()
    cycle_table = _table(
        CYCLE_PHASE_VINTAGE_SCHEMA,
        3,
        {
            "date": [date(2026, 5, 31), date(2026, 6, 30), date(2026, 5, 31)],
            "cycle_id": ["C1", "C1", "C2"],
            "vintage": ["realtime", "realtime", "latest_historical"],
            "run_id": [context.run_id] * 3,
            "as_of": [context.as_of] * 3,
            "data_vintage": [context.data_vintage] * 3,
            "model_version": [context.model_version] * 3,
            "config_hash": [context.config_hash] * 3,
            "created_at": [context.created_at] * 3,
        },
    )
    fixture = _published_run(
        tmp_path,
        include_products={"cycle_phase_vintage.parquet"},
        table_overrides={"cycle_phase_vintage.parquet": cycle_table},
    )
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT cycle_id, date, vintage FROM cycle_current ORDER BY cycle_id"
        ).fetchall() == [
            ("C1", date(2026, 6, 30), "realtime"),
            ("C2", date(2026, 5, 31), "latest_historical"),
        ]


def test_optional_products_remain_typed_empty_stable_views(tmp_path: Path) -> None:
    fixture = _published_run(
        tmp_path,
        include_products={"cycle_phase_vintage.parquet"},
    )
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        for view_name in (
            "cycle_forecast",
            "assets",
            "attribution",
            "asset_mapping_current",
            "asset_mapping_future",
            "historical_analogs",
            "scenarios",
            "cycle_evidence",
            "data_identity",
            "publication_gates",
            "calibration_log",
        ):
            assert connection.execute(
                f'SELECT count(*) FROM "{view_name}"'
            ).fetchone() == (0,)
        analog_metadata = connection.execute(
            "SELECT available, schema_json FROM _catalog_products "
            "WHERE product_name = 'historical_analogs'"
        ).fetchone()
        assert analog_metadata[0] is False
        assert "historical_date" in analog_metadata[1]


def test_required_cycle_product_is_enforced(tmp_path: Path) -> None:
    fixture = _published_run(
        tmp_path,
        include_products={"asset_mapping_current.parquet"},
    )

    with pytest.raises(CatalogBuildError, match="required"):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )


@pytest.mark.parametrize("malformation", ["missing", "type", "order"])
def test_managed_future_mapping_requires_exact_governed_schema(
    tmp_path: Path,
    malformation: str,
) -> None:
    context = _context()
    future = _core_tables(context)["asset_mapping_future.parquet"]
    if malformation == "missing":
        malformed = future.select(["scenario_id", "asset_id", "run_id"])
    elif malformation == "type":
        fields = list(future.schema)
        scenario_index = future.schema.get_field_index("scenario_id")
        fields[scenario_index] = pa.field("scenario_id", pa.int64())
        arrays = list(future.columns)
        arrays[scenario_index] = pa.chunked_array(
            [pa.array([1, 2, 3], type=pa.int64())]
        )
        malformed = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    else:
        names = list(future.schema.names)
        names[0], names[1] = names[1], names[0]
        malformed = future.select(names)
    fixture = _published_run(
        tmp_path,
        table_overrides={"asset_mapping_future.parquet": malformed},
    )

    with pytest.raises(CatalogBuildError, match="schema"):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )


@pytest.mark.parametrize(
    ("filename", "schema"),
    [
        (CYCLE_EVIDENCE_FILENAME, CYCLE_EVIDENCE_SCHEMA),
        (DATA_IDENTITY_FILENAME, DATA_IDENTITY_SCHEMA),
        (PUBLICATION_GATE_FILENAME, PUBLICATION_GATE_SCHEMA),
        (CALIBRATION_LOG_FILENAME, CALIBRATION_LOG_SCHEMA),
    ],
)
@pytest.mark.parametrize("malformation", ["missing", "type", "order"])
def test_governance_products_require_exact_product_schemas(
    tmp_path: Path,
    filename: str,
    schema: pa.Schema,
    malformation: str,
) -> None:
    malformed = _malformed_schema_table(schema, malformation)
    fixture = _published_run(
        tmp_path,
        include_products={"cycle_phase_vintage.parquet", filename},
        table_overrides={filename: malformed},
    )

    with pytest.raises(
        CatalogBuildError,
        match=rf"{re.escape(filename)} schema does not match",
    ):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )


def test_catalog_cannot_be_created_inside_immutable_run(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path)

    with pytest.raises(ValueError, match="outside|immutable run"):
        build_catalog(
            fixture.run_dir,
            fixture.run_dir / "catalog.duckdb",
            expected_manifest=fixture.manifest,
        )


@pytest.mark.parametrize("target_kind", ["symlink", "directory"])
def test_catalog_rejects_symlink_and_directory_targets(
    tmp_path: Path,
    target_kind: str,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    victim = tmp_path / "victim.duckdb"
    victim.write_bytes(b"do-not-change")
    if target_kind == "symlink":
        catalog_path.symlink_to(victim)
    else:
        catalog_path.mkdir()

    with pytest.raises(CatalogBuildError, match="regular|target"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )
    assert victim.read_bytes() == b"do-not-change"


def test_sql_path_quotes_and_injection_text_are_escaped(tmp_path: Path) -> None:
    fixture = _published_run(
        tmp_path,
        relative_parent="quoted'); DROP TABLE _catalog_metadata; --",
    )
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM _catalog_metadata"
        ).fetchone() == (1,)
        source_sql = connection.execute(
            "SELECT sql FROM duckdb_views() "
            "WHERE database_name = current_database() "
            "AND schema_name = 'main' "
            "AND view_name = '_src_cycle_phase_vintage'"
        ).fetchone()[0]
        assert "read_parquet" in source_sql
        assert "quoted''); DROP TABLE" in source_sql


def test_manifest_and_product_tamper_block_catalog_build(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path)
    product_path = fixture.run_dir / "cycle_phase_vintage.parquet"
    product_path.write_bytes(product_path.read_bytes() + b"tamper")

    with pytest.raises(ManifestVerificationError, match="checksums"):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )

    second = _published_run(tmp_path / "manifest-case")
    manifest_path = second.run_dir / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(ManifestVerificationError, match="canonical"):
        build_catalog(
            second.run_dir,
            _catalog_path(tmp_path / "manifest-case"),
            expected_manifest=second.manifest,
        )


def test_mixed_product_run_provenance_is_rejected(tmp_path: Path) -> None:
    fixture = _published_run(
        tmp_path,
        wrong_run_product="asset_mapping_future.parquet",
    )

    with pytest.raises(CatalogBuildError, match="provenance|mixed run"):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [
        ("as_of", date(2026, 6, 29)),
        ("data_vintage", date(2026, 6, 29)),
        ("model_version", "wrong-model-v1"),
        ("config_hash", "0" * 64),
        ("created_at", datetime(2026, 7, 14, 1, 2, tzinfo=timezone.utc)),
    ],
)
def test_all_present_product_provenance_must_match_manifest(
    tmp_path: Path,
    field_name: str,
    wrong_value: object,
) -> None:
    fixture = _published_run(
        tmp_path,
        provenance_override=(
            "asset_mapping_future.parquet",
            field_name,
            wrong_value,
        ),
    )

    with pytest.raises(CatalogBuildError, match="provenance"):
        build_catalog(
            fixture.run_dir,
            _catalog_path(tmp_path),
            expected_manifest=fixture.manifest,
        )


@pytest.mark.parametrize(
    ("tamper_target", "sync_metadata"),
    [
        ("scenarios", False),
        ("_src_asset_mapping_future", False),
        ("scenarios", True),
    ],
)
def test_read_only_open_reconstructs_and_verifies_all_view_definitions(
    tmp_path: Path,
    tamper_target: str,
    sync_metadata: bool,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    if tamper_target == "scenarios":
        replacement_sql = (
            "CREATE OR REPLACE VIEW scenarios AS "
            f"SELECT '{fixture.manifest.run_id}' AS run_id, "
            "'pwned' AS scenario_id"
        )
    else:
        future_path = next(fixture.run_dir.rglob("asset_mapping_future.parquet"))
        escaped_path = str(future_path).replace("'", "''")
        replacement_sql = (
            "CREATE OR REPLACE VIEW _src_asset_mapping_future AS "
            f"SELECT * FROM read_parquet('{escaped_path}') WHERE FALSE"
        )
    with duckdb.connect(str(catalog_path)) as connection:
        connection.execute(replacement_sql)
        if sync_metadata:
            tampered_checksum = _checksum(replacement_sql.encode("utf-8"))
            connection.execute(
                "UPDATE _catalog_metadata SET views_sql_checksum = ?, "
                "catalog_checksum = ?",
                [tampered_checksum, tampered_checksum],
            )
            connection.execute(
                "UPDATE _catalog_views SET definition_checksum = ?",
                [tampered_checksum],
            )
        connection.execute("CHECKPOINT")

    with pytest.raises(CatalogVerificationError, match="view|metadata|definition"):
        open_catalog(
            catalog_path,
            run_dir=fixture.run_dir,
            expected_manifest=fixture.manifest,
        )


def test_clean_reopen_compares_semantic_plans_not_raw_view_sql(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    future_path = next(fixture.run_dir.rglob("asset_mapping_future.parquet"))
    escaped_path = str(future_path).replace("'", "''")
    with duckdb.connect(str(catalog_path)) as connection:
        connection.execute(
            "CREATE OR REPLACE VIEW _src_asset_mapping_future AS "
            f"SELECT * FROM read_parquet('{escaped_path}') WHERE TRUE"
        )
        connection.execute("CHECKPOINT")

    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert connection.execute(
            "SELECT count(*) FROM asset_mapping_future"
        ).fetchone() == (3,)


def test_clean_assets_reopen_compares_actual_and_expected_query_bodies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    explained_queries: list[str] = []
    real_normalized_explain = catalog_api._normalized_explain

    def capture_explain(
        connection: duckdb.DuckDBPyConnection,
        query: str,
    ) -> tuple[tuple[str, str], ...]:
        explained_queries.append(query)
        return real_normalized_explain(connection, query)

    monkeypatch.setattr(catalog_api, "_normalized_explain", capture_explain)
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert connection.execute("SELECT count(*) FROM assets").fetchone() == (2,)

    assert all(not query.startswith('SELECT * FROM "') for query in explained_queries)
    asset_bodies = [
        query
        for query in explained_queries
        if "SELECT DISTINCT run_id, asset_id" in query
    ]
    assert len(asset_bodies) == 2


def test_idempotent_rebuild_and_read_only_reopen(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    first = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        first_metadata = connection.execute(
            "SELECT * FROM _catalog_metadata"
        ).fetchall()
        first_views = connection.execute(
            "SELECT view_name, sql FROM duckdb_views() "
            "WHERE database_name = current_database() AND schema_name = 'main' "
            "ORDER BY view_name"
        ).fetchall()

    second = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    assert second == first
    connection = open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    )
    try:
        assert connection.execute("SELECT * FROM _catalog_metadata").fetchall() == (
            first_metadata
        )
        assert (
            connection.execute(
                "SELECT view_name, sql FROM duckdb_views() "
                "WHERE database_name = current_database() AND schema_name = 'main' "
                "ORDER BY view_name"
            ).fetchall()
            == first_views
        )
        with pytest.raises(duckdb.InvalidInputException, match="read-only"):
            connection.execute("CREATE TABLE forbidden(value INTEGER)")
    finally:
        connection.close()


def _build_catalog_with_prior_device_identity(
    fixture: _PublishedFixture,
    catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> catalog_api.CatalogBuildResult:
    snapshot_file = catalog_api._snapshot_file

    def previous_device_snapshot(*args: object, **kwargs: object):
        snapshot = snapshot_file(*args, **kwargs)
        return replace(snapshot, device=snapshot.device + 1_000_000)

    with monkeypatch.context() as context:
        context.setattr(catalog_api, "_snapshot_file", previous_device_snapshot)
        return build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )


def test_explicit_repair_rebuilds_only_uniform_device_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    _build_catalog_with_prior_device_identity(fixture, catalog_path, monkeypatch)
    previous_identity = catalog_path.lstat().st_dev, catalog_path.lstat().st_ino

    with pytest.raises(CatalogVerificationError, match="metadata|paths"):
        open_catalog(
            catalog_path,
            run_dir=fixture.run_dir,
            expected_manifest=fixture.manifest,
        )

    result = repair_catalog_device_identity_drift(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result is not None
    assert result.run_id == fixture.manifest.run_id
    assert (catalog_path.lstat().st_dev, catalog_path.lstat().st_ino) != (
        previous_identity
    )
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert connection.execute("SELECT run_id FROM runs").fetchone() == (
            fixture.manifest.run_id,
        )


def test_explicit_repair_leaves_healthy_catalog_identity_unchanged(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    catalog_identity = catalog_path.lstat().st_dev, catalog_path.lstat().st_ino

    result = repair_catalog_device_identity_drift(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result is None
    assert (catalog_path.lstat().st_dev, catalog_path.lstat().st_ino) == (
        catalog_identity
    )


def test_device_drift_repair_refuses_catalog_audit_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    _build_catalog_with_prior_device_identity(fixture, catalog_path, monkeypatch)
    with duckdb.connect(str(catalog_path)) as connection:
        connection.execute(
            "UPDATE _catalog_metadata SET catalog_checksum = ?",
            ["0" * 64],
        )
        connection.execute("CHECKPOINT")
    catalog_identity = catalog_path.lstat().st_dev, catalog_path.lstat().st_ino

    with pytest.raises(CatalogRepairRefusedError, match="audit checksum"):
        repair_catalog_device_identity_drift(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )

    assert (catalog_path.lstat().st_dev, catalog_path.lstat().st_ino) == (
        catalog_identity
    )
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT catalog_checksum FROM _catalog_metadata"
        ).fetchone() == ("0" * 64,)


def test_device_drift_repair_refuses_invalid_immutable_product_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    _build_catalog_with_prior_device_identity(fixture, catalog_path, monkeypatch)
    catalog_identity = catalog_path.lstat().st_dev, catalog_path.lstat().st_ino
    product_path = fixture.run_dir / "cycle_phase_vintage.parquet"
    product_path.write_bytes(product_path.read_bytes() + b"tampered")

    with pytest.raises(ManifestVerificationError, match="checksums"):
        repair_catalog_device_identity_drift(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )

    assert (catalog_path.lstat().st_dev, catalog_path.lstat().st_ino) == (
        catalog_identity
    )


def test_startup_repair_atomically_updates_catalog_and_both_deployments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from seven_cycle_platform.deployment import write_deployment_manifest
    from seven_cycle_platform.local_service import (
        repair_latest_catalog_device_drift,
    )

    fixture = _published_run(tmp_path)
    catalog_root = tmp_path / "startup-catalogs"
    catalog_root.mkdir()
    catalog_path = catalog_root / f"{fixture.manifest.run_id}.duckdb"
    previous_catalog = _build_catalog_with_prior_device_identity(
        fixture,
        catalog_path,
        monkeypatch,
    )
    web_root = tmp_path / "startup-web"
    (web_root / "data").mkdir(parents=True)
    (web_root / "index.html").write_text("<title>Circle</title>", encoding="utf-8")
    write_deployment_manifest(
        product_root=fixture.product_root,
        catalog_checksum=previous_catalog.catalog_checksum,
        run_id=fixture.manifest.run_id,
        deployment_as_of=fixture.manifest.as_of,
        web_root=web_root,
    )
    latest_path = fixture.product_root / "latest.json"
    latest_before = _path_state(latest_path)
    run_before = _run_state(fixture.run_dir)

    repaired = repair_latest_catalog_device_drift(
        fixture.product_root,
        catalog_root,
        web_root,
    )

    assert repaired["action"] == "repaired_device_drift"
    assert repaired["catalog_checksum"] != previous_catalog.catalog_checksum
    product_deployment = (fixture.product_root / "deployment.json").read_bytes()
    web_deployment = (web_root / "data" / "deployment.json").read_bytes()
    assert product_deployment == web_deployment
    deployment = json.loads(product_deployment)
    assert deployment["catalog_checksum"] == repaired["catalog_checksum"]
    assert deployment["deployment_id"] == repaired["deployment_id"]
    assert _path_state(latest_path) == latest_before
    assert _run_state(fixture.run_dir) == run_before
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert connection.execute(
            "SELECT catalog_checksum FROM runs"
        ).fetchone() == (repaired["catalog_checksum"],)


def test_failed_rebuild_preserves_existing_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    before = catalog_path.read_bytes()

    def fail_build(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected build failure")

    monkeypatch.setattr(catalog_api, "_create_catalog_database", fail_build)
    with pytest.raises(CatalogBuildError, match="failed safely"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )
    assert catalog_path.read_bytes() == before
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)


def test_post_replace_failure_rolls_back_existing_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    before = catalog_path.read_bytes()
    real_fsync_directory = catalog_api._fsync_directory
    injected = False

    def fail_once(directory: Path) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected directory fsync failure")
        real_fsync_directory(directory)

    monkeypatch.setattr(catalog_api, "_fsync_directory", fail_once)
    with pytest.raises(CatalogBuildError, match="failed safely"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )

    assert catalog_path.read_bytes() == before
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)


def test_first_build_post_commit_rmdir_failure_keeps_committed_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    real_rmdir = Path.rmdir

    def fail_catalog_temp_rmdir(path: Path) -> None:
        if path.parent == catalog_path.parent and path.name.startswith(
            f".{catalog_path.name}."
        ):
            raise OSError("injected committed temp cleanup failure")
        real_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", fail_catalog_temp_rmdir)
    result = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result.path == catalog_path
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)


def test_rebuild_post_commit_backup_unlink_failure_keeps_new_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    original_inode = catalog_path.stat().st_ino
    real_unlink = Path.unlink

    def fail_backup_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name == "previous.duckdb":
            raise OSError("injected committed backup cleanup failure")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_backup_unlink)
    result = build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    assert result.path == catalog_path
    assert catalog_path.stat().st_ino != original_inode
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)


def test_first_build_precommit_fsync_failure_removes_uncommitted_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    real_fsync_directory = catalog_api._fsync_directory
    injected = False

    def fail_once(directory: Path) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected first-build fsync failure")
        real_fsync_directory(directory)

    monkeypatch.setattr(catalog_api, "_fsync_directory", fail_once)
    with pytest.raises(CatalogBuildError, match="failed safely"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )
    assert not catalog_path.exists()


def test_failed_rollback_preserves_old_catalog_backup_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    old_catalog = catalog_path.read_bytes()
    real_replace = os.replace
    real_fsync_directory = catalog_api._fsync_directory
    injected_fsync = False

    def fail_commit_fsync(directory: Path) -> None:
        nonlocal injected_fsync
        if not injected_fsync:
            injected_fsync = True
            raise OSError("injected precommit fsync failure")
        real_fsync_directory(directory)

    def fail_restore(source: Path, target: Path) -> None:
        if Path(source).name == "previous.duckdb":
            raise OSError("injected rollback replace failure")
        real_replace(source, target)

    monkeypatch.setattr(catalog_api, "_fsync_directory", fail_commit_fsync)
    monkeypatch.setattr(os, "replace", fail_restore)
    with pytest.raises(CatalogBuildError, match="rollback was incomplete"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )

    backups = list(catalog_path.parent.glob(f".{catalog_path.name}.*/previous.duckdb"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_catalog


def test_concurrent_catalog_target_is_rejected_without_overwrite(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    before = catalog_path.read_bytes()
    lock_path = catalog_path.with_name(f".{catalog_path.name}.lock")
    lock_path.write_text("active builder", encoding="utf-8")

    with pytest.raises(CatalogBuildError, match="concurrently"):
        build_catalog(
            fixture.run_dir,
            catalog_path,
            expected_manifest=fixture.manifest,
        )
    assert catalog_path.read_bytes() == before
    assert lock_path.read_text(encoding="utf-8") == "active builder"


def test_build_and_queries_do_not_change_run_products_or_latest(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    run_before = _run_state(fixture.run_dir)
    latest_path = fixture.product_root / "latest.json"
    latest_before = _path_state(latest_path)

    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        for view_name in STABLE_VIEW_NAMES:
            connection.execute(f'SELECT * FROM "{view_name}"').fetchall()

    assert _run_state(fixture.run_dir) == run_before
    assert _path_state(latest_path) == latest_before


def test_read_only_open_detects_same_checksum_product_replacement(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    product_path = fixture.run_dir / "cycle_phase_vintage.parquet"
    original_path = tmp_path / "cycle_phase_vintage.original"
    product_path.rename(original_path)
    shutil.copyfile(original_path, product_path)
    assert os.stat(product_path).st_ino != os.stat(original_path).st_ino

    with pytest.raises(CatalogVerificationError, match="replaced|metadata"):
        open_catalog(
            catalog_path,
            run_dir=fixture.run_dir,
            expected_manifest=fixture.manifest,
        )


def test_open_connection_rejects_product_overwrite_before_next_query(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    connection = open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    )
    try:
        cycle_path = fixture.run_dir / "cycle_phase_vintage.parquet"
        table = pq.read_table(cycle_path)
        tampered = _replace_column(
            table,
            "cycle_id",
            ["ZZ"] * table.num_rows,
        )
        pq.write_table(tampered, cycle_path)

        with pytest.raises(CatalogVerificationError):
            connection.execute("SELECT cycle_id FROM cycle_history").fetchall()
    finally:
        connection.close()


def test_open_connection_rechecks_products_before_fetch(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    connection = open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    )
    try:
        connection.execute("SELECT cycle_id FROM cycle_history ORDER BY cycle_id")
        product_path = fixture.run_dir / "cycle_phase_vintage.parquet"
        original_path = tmp_path / "cycle_phase_vintage.fetch-original"
        product_path.rename(original_path)
        shutil.copyfile(original_path, product_path)

        with pytest.raises(CatalogVerificationError):
            connection.fetchall()
    finally:
        connection.close()


def test_open_connection_rejects_manifest_path_replacement_before_execute(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    connection = open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    )
    try:
        manifest_path = fixture.run_dir / "manifest.json"
        original_inode = manifest_path.stat().st_ino
        original_manifest = tmp_path / "manifest.original.json"
        manifest_path.rename(original_manifest)
        manifest_path.write_bytes(original_manifest.read_bytes() + b" ")
        assert manifest_path.stat().st_ino != original_inode

        with pytest.raises(CatalogVerificationError):
            connection.execute("SELECT count(*) FROM runs")
    finally:
        connection.close()


def test_open_connection_rejects_catalog_path_replacement_before_fetch(
    tmp_path: Path,
) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    connection = open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    )
    try:
        connection.execute("SELECT run_id FROM runs")
        original_inode = catalog_path.stat().st_ino
        original_catalog = tmp_path / "products.original.duckdb"
        catalog_path.rename(original_catalog)
        shutil.copyfile(original_catalog, catalog_path)
        assert catalog_path.stat().st_ino != original_inode

        with pytest.raises(CatalogVerificationError):
            connection.fetchall()
    finally:
        connection.close()


def test_open_catalog_returns_controlled_connection_surface(tmp_path: Path) -> None:
    fixture = _published_run(tmp_path)
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    with open_catalog(
        catalog_path,
        run_dir=fixture.run_dir,
        expected_manifest=fixture.manifest,
    ) as connection:
        assert not isinstance(connection, duckdb.DuckDBPyConnection)
        assert not hasattr(connection, "cursor")
        assert not hasattr(connection, "sql")
        assert connection.execute("SELECT count(*) FROM runs").fetchone() == (1,)
        assert connection.execute("SELECT 1 AS value").fetchdf().iloc[0, 0] == 1
        arrow_table = connection.execute("SELECT run_id FROM runs").fetch_arrow_table()
        assert arrow_table.num_rows == 1


def test_secret_like_values_do_not_enter_catalog_or_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "dummy-secret-value-12345"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    fixture = _published_run(
        tmp_path,
        quality_summary={
            "checks": {
                "error": f"upstream echoed {secret}",
                "url": f"https://example.test/?api_key={secret}",
            }
        },
    )
    catalog_path = _catalog_path(tmp_path)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )
    assert secret.encode() not in catalog_path.read_bytes()
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        metadata_text = repr(
            connection.execute(
                "SELECT * FROM _catalog_metadata, _catalog_products, "
                "_catalog_quality_summary"
            ).fetchall()
        )
        assert secret not in metadata_text
        assert "[REDACTED]" in metadata_text

    secret_root = tmp_path / f"api_key={secret}"
    unsafe_fixture = _published_run(secret_root)
    with pytest.raises(CatalogBuildError) as captured:
        build_catalog(
            unsafe_fixture.run_dir,
            _catalog_path(secret_root),
            expected_manifest=unsafe_fixture.manifest,
        )
    assert secret not in str(captured.value)


def test_large_quality_metadata_uses_bounded_batch_scans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row_count = 12_000
    findings = _table(
        QUALITY_FINDING_SCHEMA,
        row_count,
        {
            "entity_id": [f"entity-{index % 17}" for index in range(row_count)],
            "check": [f"check-{index:05d}" for index in range(row_count)],
            "severity": ["info"] * row_count,
            "status": ["passed"] * row_count,
            "message": ["bounded batch fixture"] * row_count,
            "observed_value": [1.0] * row_count,
            "threshold": [1.0] * row_count,
        },
    )
    fixture = _published_run(
        tmp_path,
        table_overrides={"quality_findings.parquet": findings},
    )
    catalog_path = _catalog_path(tmp_path)

    def reject_full_table_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("full-table pq.read_table is forbidden")

    monkeypatch.setattr(catalog_api.pq, "read_table", reject_full_table_read)
    build_catalog(
        fixture.run_dir,
        catalog_path,
        expected_manifest=fixture.manifest,
    )

    source = Path(catalog_api.__file__).read_text(encoding="utf-8")
    assert ".to_pylist(" not in source
    with duckdb.connect(str(catalog_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM quality_findings"
        ).fetchone() == (row_count + 3,)
