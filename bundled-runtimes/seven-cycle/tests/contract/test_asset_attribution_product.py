from datetime import date, datetime, timezone
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.storage import RunContext, publish_run
from seven_cycle_platform.storage.manifest import sha256_file


PROVENANCE_COLUMNS = [
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
]
ATTRIBUTION_COLUMNS = [
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
    "significance",
    "is_explained",
    "is_residual",
    "observed_return",
    "reconstructed_return",
    "interval_status",
    "status",
    "evidence_level",
    "effective_samples",
    "draw_count",
    *PROVENANCE_COLUMNS,
]
CONSERVATION_COLUMNS = [
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
    *PROVENANCE_COLUMNS,
]


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2024, 6, 30),
        data_vintage=date(2024, 6, 30),
        model_version="seven-cycle-v1",
        config={"attribution_draws": 500, "intervals": [0.5, 0.8]},
        input_checksums={"attribution.parquet": _checksum(b"attribution")},
        quality_summary={"failed": 0, "passed": 2},
        created_at=datetime(2026, 7, 13, 8, 15, tzinfo=timezone.utc),
    )


def _frames(*, unavailable: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    component_rows = (
        (
            "benchmark",
            "benchmark_return",
            0.40,
            0.30,
            0.50,
            0.20,
            0.60,
            "positive",
            True,
            False,
            "estimated",
            "high",
        ),
        (
            "event",
            "policy",
            -0.20,
            -0.28,
            -0.12,
            -0.35,
            -0.05,
            "negative",
            True,
            False,
            "parent_informed",
            "medium",
        ),
        (
            "asset_residual",
            "asset_residual",
            0.80,
            0.50,
            1.10,
            -0.20,
            1.40,
            "not_significant",
            False,
            True,
            "estimated",
            "high",
        ),
    )
    rows: list[dict[str, object]] = []
    for basis in ("absolute", "excess"):
        for (
            component_type,
            component_id,
            point,
            lower_50,
            upper_50,
            lower_80,
            upper_80,
            significance,
            is_explained,
            is_residual,
            status,
            evidence_level,
        ) in component_rows:
            interval_status = "available"
            effective_samples = 36
            if unavailable and component_type == "asset_residual":
                lower_50 = upper_50 = lower_80 = upper_80 = np.nan
                significance = "unavailable"
                interval_status = "unavailable"
                evidence_level = "low"
                effective_samples = 6
            rows.append(
                {
                    "asset_id": "asset_a",
                    "period_start": pd.Timestamp("2024-04-30"),
                    "period_end": pd.Timestamp("2024-06-30"),
                    "horizon_months": 3,
                    "return_basis": basis,
                    "component_type": component_type,
                    "component_id": component_id,
                    "point_contribution": point,
                    "lower_50": lower_50,
                    "upper_50": upper_50,
                    "lower_80": lower_80,
                    "upper_80": upper_80,
                    "significance": significance,
                    "is_explained": is_explained,
                    "is_residual": is_residual,
                    "observed_return": 1.0,
                    "reconstructed_return": 1.0,
                    "interval_status": interval_status,
                    "status": status,
                    "evidence_level": evidence_level,
                    "effective_samples": effective_samples,
                    "draw_count": 500,
                }
            )
    available_count = 2 if unavailable else 3
    unavailable_count = 1 if unavailable else 0
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "asset_a",
                "period_start": pd.Timestamp("2024-04-30"),
                "period_end": pd.Timestamp("2024-06-30"),
                "horizon_months": 3,
                "return_basis": basis,
                "point_component_sum": 1.0,
                "observed_return": 1.0,
                "point_conservation_error": 0.0,
                "max_draw_conservation_error": np.nan if unavailable else 0.0,
                "available_component_count": available_count,
                "unavailable_component_count": unavailable_count,
                "status": "partial" if unavailable else "available",
            }
            for basis in ("absolute", "excess")
        ]
    )
    return pd.DataFrame(rows), diagnostics


def _interval_result(
    intervals: pd.DataFrame | None = None,
    diagnostics: pd.DataFrame | None = None,
    *,
    sync_bounds: bool = True,
) -> object:
    attribution = __import__(
        "seven_cycle_platform.attribution",
        fromlist=["AttributionIntervalResult"],
    )
    if intervals is None or diagnostics is None:
        intervals, diagnostics = _frames()
    intervals = intervals.copy(deep=True)
    diagnostics = diagnostics.copy(deep=True)
    intervals = intervals.loc[:, attribution.ATTRIBUTION_INTERVAL_COLUMNS]
    diagnostics = diagnostics.loc[
        :, attribution.ATTRIBUTION_INTERVAL_DIAGNOSTIC_COLUMNS
    ]
    draw_count = 500
    draw_rows: list[dict[str, object]] = []

    def draws_from_bounds(row: pd.Series) -> np.ndarray:
        positions = np.asarray(
            [0.0, 0.10, 0.25, 0.75, 0.90, 1.0],
            dtype="float64",
        ) * (draw_count - 1)
        lower_padding = max(float(row["lower_50"] - row["lower_80"]), 1e-6)
        upper_padding = max(float(row["upper_80"] - row["upper_50"]), 1e-6)
        values = np.asarray(
            [
                row["lower_80"] - lower_padding,
                row["lower_80"],
                row["lower_50"],
                row["upper_50"],
                row["upper_80"],
                row["upper_80"] + upper_padding,
            ],
            dtype="float64",
        )
        return np.interp(np.arange(draw_count), positions, values)

    available_groups = (
        diagnostics.loc[diagnostics["status"].eq("available")]
        if sync_bounds
        else diagnostics.iloc[0:0]
    )
    for diagnostic in available_groups.itertuples(index=False):
        group_mask = (
            intervals["asset_id"].eq(diagnostic.asset_id)
            & intervals["period_start"].eq(diagnostic.period_start)
            & intervals["period_end"].eq(diagnostic.period_end)
            & intervals["horizon_months"].eq(diagnostic.horizon_months)
            & intervals["return_basis"].eq(diagnostic.return_basis)
        )
        group = intervals.loc[group_mask]
        residual_indices = group.index[group["component_type"].eq("asset_residual")]
        assert len(residual_indices) == 1
        residual_index = residual_indices[0]
        component_draws = {
            index: draws_from_bounds(row)
            for index, row in group.drop(index=residual_index).iterrows()
        }
        residual_draws = float(diagnostic.observed_return) - np.add.reduce(
            list(component_draws.values()),
            axis=0,
        )
        component_draws[residual_index] = residual_draws
        if sync_bounds:
            for index, values in component_draws.items():
                lower_80, lower_50, upper_50, upper_80 = np.quantile(
                    values,
                    [0.10, 0.25, 0.75, 0.90],
                    method="linear",
                ).tolist()
                intervals.loc[
                    index,
                    ["lower_50", "upper_50", "lower_80", "upper_80"],
                ] = [lower_50, upper_50, lower_80, upper_80]
                intervals.loc[index, "significance"] = (
                    "positive"
                    if lower_80 > 0.0
                    else "negative"
                    if upper_80 < 0.0
                    else "not_significant"
                )
        for index, component in intervals.loc[group.index].iterrows():
            draw_rows.extend(
                {
                    "asset_id": component["asset_id"],
                    "period_start": component["period_start"],
                    "period_end": component["period_end"],
                    "horizon_months": component["horizon_months"],
                    "return_basis": component["return_basis"],
                    "draw": draw,
                    "component_type": component["component_type"],
                    "component_id": component["component_id"],
                    "contribution": component_draws[index][draw],
                    "target_return": component["observed_return"],
                }
                for draw in range(draw_count)
            )
    draws = pd.DataFrame.from_records(
        draw_rows,
        columns=attribution.ATTRIBUTION_DRAW_COLUMNS,
    )
    return attribution.AttributionIntervalResult(
        intervals=intervals,
        diagnostics=diagnostics,
        draws=draws,
        draw_count=draw_count,
        seed=17,
    )


def _product_api() -> object:
    try:
        return __import__(
            "seven_cycle_platform.products.asset_attribution",
            fromlist=["asset_attribution"],
        )
    except ModuleNotFoundError as error:
        pytest.fail(f"Task 17 product module is missing: {error}", pytrace=False)


def test_asset_attribution_arrow_schemas_are_exact_and_stable() -> None:
    try:
        contracts = __import__(
            "seven_cycle_platform.contracts.arrow",
            fromlist=["ASSET_ATTRIBUTION_SCHEMA"],
        )
        attribution_schema = contracts.ASSET_ATTRIBUTION_SCHEMA
        conservation_schema = contracts.ASSET_ATTRIBUTION_CONSERVATION_SCHEMA
    except (AttributeError, ImportError) as error:
        pytest.fail(f"Task 17 Arrow schemas are missing: {error}", pytrace=False)

    attribution_types = {
        "asset_id": pa.string(),
        "period_start": pa.date32(),
        "period_end": pa.date32(),
        "horizon_months": pa.int32(),
        "return_basis": pa.string(),
        "component_type": pa.string(),
        "component_id": pa.string(),
        "point_contribution": pa.float64(),
        "lower_50": pa.float64(),
        "upper_50": pa.float64(),
        "lower_80": pa.float64(),
        "upper_80": pa.float64(),
        "significance": pa.string(),
        "is_explained": pa.bool_(),
        "is_residual": pa.bool_(),
        "observed_return": pa.float64(),
        "reconstructed_return": pa.float64(),
        "interval_status": pa.string(),
        "status": pa.string(),
        "evidence_level": pa.string(),
        "effective_samples": pa.int32(),
        "draw_count": pa.int32(),
        "run_id": pa.string(),
        "as_of": pa.date32(),
        "data_vintage": pa.date32(),
        "model_version": pa.string(),
        "config_hash": pa.string(),
        "created_at": pa.timestamp("us", tz="UTC"),
    }
    conservation_types = {
        "asset_id": pa.string(),
        "period_start": pa.date32(),
        "period_end": pa.date32(),
        "horizon_months": pa.int32(),
        "return_basis": pa.string(),
        "point_component_sum": pa.float64(),
        "observed_return": pa.float64(),
        "point_conservation_error": pa.float64(),
        "max_draw_conservation_error": pa.float64(),
        "available_component_count": pa.int32(),
        "unavailable_component_count": pa.int32(),
        "status": pa.string(),
        "run_id": pa.string(),
        "as_of": pa.date32(),
        "data_vintage": pa.date32(),
        "model_version": pa.string(),
        "config_hash": pa.string(),
        "created_at": pa.timestamp("us", tz="UTC"),
    }

    assert attribution_schema.names == ATTRIBUTION_COLUMNS
    assert {field.name: field.type for field in attribution_schema} == attribution_types
    assert conservation_schema.names == CONSERVATION_COLUMNS
    assert {
        field.name: field.type for field in conservation_schema
    } == conservation_types


def test_builder_has_unique_dimensions_context_provenance_and_two_bases() -> None:
    api = _product_api()
    intervals, diagnostics = _frames()
    intervals_before = intervals.copy(deep=True)
    diagnostics_before = diagnostics.copy(deep=True)
    context = _context()

    product = api.build_asset_attribution(
        _interval_result(intervals, diagnostics), context=context
    )
    repeated = api.build_asset_attribution(
        _interval_result(intervals, diagnostics), context=context
    )

    pd.testing.assert_frame_equal(intervals, intervals_before, check_exact=True)
    pd.testing.assert_frame_equal(diagnostics, diagnostics_before, check_exact=True)
    pd.testing.assert_frame_equal(
        product.attribution,
        repeated.attribution,
        check_exact=True,
    )
    pd.testing.assert_frame_equal(
        product.conservation,
        repeated.conservation,
        check_exact=True,
    )
    assert list(product.attribution.columns) == ATTRIBUTION_COLUMNS
    assert list(product.conservation.columns) == CONSERVATION_COLUMNS
    dimensions = [
        "asset_id",
        "period_start",
        "period_end",
        "horizon_months",
        "return_basis",
        "component_type",
        "component_id",
    ]
    assert not product.attribution.duplicated(dimensions).any()
    assert set(product.attribution["return_basis"]) == {"absolute", "excess"}
    assert len(product.attribution) == 6
    for field_name in PROVENANCE_COLUMNS:
        assert product.attribution[field_name].nunique() == 1
        assert product.conservation[field_name].nunique() == 1
    assert product.attribution["run_id"].eq(context.run_id).all()
    assert product.conservation["run_id"].eq(context.run_id).all()
    api.validate_asset_attribution(product, context=context)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda intervals, diagnostics: (
                pd.concat([intervals, intervals.iloc[[0]]], ignore_index=True),
                diagnostics,
            ),
            "dimensions must be unique",
        ),
        (
            lambda intervals, diagnostics: (
                intervals.assign(
                    lower_50=lambda values: np.where(
                        values.index == 0, values["lower_80"] - 0.1, values["lower_50"]
                    )
                ),
                diagnostics,
            ),
            "nested",
        ),
        (
            lambda intervals, diagnostics: (
                intervals.assign(
                    significance=lambda values: np.where(
                        values.index == 0, "negative", values["significance"]
                    )
                ),
                diagnostics,
            ),
            "significance",
        ),
        (
            lambda intervals, diagnostics: (
                intervals.assign(horizon_months=0),
                diagnostics,
            ),
            "horizon_months",
        ),
        (
            lambda intervals, diagnostics: (
                intervals.assign(return_basis="relative"),
                diagnostics,
            ),
            "return_basis",
        ),
        (
            lambda intervals, diagnostics: (
                intervals.assign(period_start=pd.Timestamp("2024-07-31")),
                diagnostics,
            ),
            "period_start",
        ),
    ],
)
def test_builder_rejects_malformed_interval_contracts(mutation, message: str) -> None:
    api = _product_api()
    intervals, diagnostics = mutation(*_frames())

    with pytest.raises((TypeError, ValueError), match=message):
        api.build_asset_attribution(
            _interval_result(intervals, diagnostics, sync_bounds=False),
            context=_context(),
        )


def test_builder_rejects_fabricated_unavailable_bounds_and_caller_provenance() -> None:
    api = _product_api()
    intervals, diagnostics = _frames(unavailable=True)
    fabricated = intervals.copy(deep=True)
    fabricated.loc[fabricated["interval_status"].eq("unavailable"), "lower_50"] = 0.0
    with pytest.raises(ValueError, match="unavailable.*bounds"):
        api.build_asset_attribution(
            _interval_result(fabricated, diagnostics), context=_context()
        )

    with pytest.raises(TypeError, match="validated draws"):
        api.build_asset_attribution(intervals, diagnostics, context=_context())


def test_builder_rejects_point_and_diagnostic_conservation_mismatch() -> None:
    api = _product_api()
    intervals, diagnostics = _frames()
    intervals.loc[0, "point_contribution"] += 0.01
    with pytest.raises(ValueError, match="point contribution"):
        api.build_asset_attribution(
            _interval_result(intervals, diagnostics), context=_context()
        )

    intervals, diagnostics = _frames()
    diagnostics.loc[0, "available_component_count"] = 2
    with pytest.raises(ValueError, match="availability counts"):
        api.build_asset_attribution(
            _interval_result(intervals, diagnostics), context=_context()
        )


def test_builder_and_validator_reject_mixed_draw_count() -> None:
    api = _product_api()
    intervals, diagnostics = _frames()
    intervals.loc[0, "draw_count"] = 501

    with pytest.raises(ValueError, match="draw_count must be constant"):
        api.build_asset_attribution(
            _interval_result(intervals, diagnostics), context=_context()
        )


def test_writer_is_byte_deterministic_and_refuses_overwrite(tmp_path: Path) -> None:
    api = _product_api()
    context = _context()
    intervals, diagnostics = _frames(unavailable=True)
    source_result = _interval_result(intervals, diagnostics)
    product = api.build_asset_attribution(source_result, context=context)
    attribution = __import__(
        "seven_cycle_platform.attribution",
        fromlist=["AttributionIntervalResult"],
    )
    shuffled_source = attribution.AttributionIntervalResult(
        intervals=source_result.intervals.sample(frac=1.0, random_state=13).reset_index(
            drop=True
        ),
        diagnostics=source_result.diagnostics.sample(
            frac=1.0, random_state=13
        ).reset_index(drop=True),
        draws=source_result.draws,
        draw_count=source_result.draw_count,
        seed=source_result.seed,
    )
    shuffled = api.build_asset_attribution(shuffled_source, context=context)
    first_dir = tmp_path / "first" / context.run_id
    second_dir = tmp_path / "second" / context.run_id
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)

    first_paths = api.write_asset_attribution(first_dir, product, context=context)
    second_paths = api.write_asset_attribution(second_dir, shuffled, context=context)

    assert first_paths[0].name == api.ASSET_ATTRIBUTION_FILENAME
    assert first_paths[1].name == api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME
    assert first_paths[0].read_bytes() == second_paths[0].read_bytes()
    assert first_paths[1].read_bytes() == second_paths[1].read_bytes()
    with pytest.raises(FileExistsError, match="refuse.*overwrite"):
        api.write_asset_attribution(first_dir, product, context=context)


def test_writer_rejects_manually_assembled_or_raw_products(tmp_path: Path) -> None:
    api = _product_api()
    context = _context()
    product = api.build_asset_attribution(_interval_result(), context=context)

    with pytest.raises(TypeError, match="build_asset_attribution"):
        api.AssetAttributionProduct(
            attribution=product.attribution,
            conservation=product.conservation,
        )

    run_dir = tmp_path / context.run_id
    run_dir.mkdir()
    with pytest.raises(TypeError, match="returned by build_asset_attribution"):
        api.write_asset_attribution(
            run_dir,
            product.attribution,
            product.conservation,
            context=context,
        )


def test_writer_cleans_both_files_when_second_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _product_api()
    context = _context()
    product = api.build_asset_attribution(_interval_result(), context=context)
    run_dir = tmp_path / context.run_id
    run_dir.mkdir()
    original = api.pq.write_table
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second product failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(api.pq, "write_table", fail_second)

    with pytest.raises(OSError, match="second product"):
        api.write_asset_attribution(run_dir, product, context=context)
    assert not (run_dir / api.ASSET_ATTRIBUTION_FILENAME).exists()
    assert not (run_dir / api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME).exists()


def test_writer_never_unlinks_a_concurrent_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _product_api()
    context = _context()
    product = api.build_asset_attribution(_interval_result(), context=context)
    run_dir = tmp_path / context.run_id
    run_dir.mkdir()
    concurrent_bytes = b"concurrent valid owner"
    original_link = api.os.link

    def race_link(source, destination, *args, **kwargs):
        destination_path = Path(destination)
        if destination_path.name == api.ASSET_ATTRIBUTION_FILENAME:
            with destination_path.open("xb") as concurrent_file:
                concurrent_file.write(concurrent_bytes)
            raise FileExistsError("simulated concurrent publish")
        return original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(api.os, "link", race_link)

    with pytest.raises(FileExistsError, match="concurrent|overwrite"):
        api.write_asset_attribution(run_dir, product, context=context)
    assert (run_dir / api.ASSET_ATTRIBUTION_FILENAME).read_bytes() == concurrent_bytes
    assert not (run_dir / api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME).exists()


def test_atomic_publish_manifest_contains_both_checksums_and_schemas(
    tmp_path: Path,
) -> None:
    api = _product_api()
    contracts = __import__(
        "seven_cycle_platform.contracts.arrow",
        fromlist=["ASSET_ATTRIBUTION_SCHEMA"],
    )
    context = _context()
    product = api.build_asset_attribution(_interval_result(), context=context)
    product_root = tmp_path / "products" / "seven_cycle"

    def write_staging(staging_dir: Path) -> None:
        api.write_asset_attribution(staging_dir, product, context=context)

    def validate_staging(staging_dir: Path, manifest: object) -> None:
        attribution_path = staging_dir / api.ASSET_ATTRIBUTION_FILENAME
        conservation_path = staging_dir / api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME
        assert manifest.product_checksums == {
            api.ASSET_ATTRIBUTION_FILENAME: sha256_file(attribution_path),
            api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME: sha256_file(conservation_path),
        }
        assert (
            pq.read_table(attribution_path).schema == contracts.ASSET_ATTRIBUTION_SCHEMA
        )
        assert (
            pq.read_table(conservation_path).schema
            == contracts.ASSET_ATTRIBUTION_CONSERVATION_SCHEMA
        )
        api.validate_asset_attribution(
            pd.read_parquet(attribution_path),
            pd.read_parquet(conservation_path),
            context=context,
        )

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
        validate_staging=validate_staging,
    )

    run_dir = product_root / "runs" / context.run_id
    expected = {
        api.ASSET_ATTRIBUTION_FILENAME: sha256_file(
            run_dir / api.ASSET_ATTRIBUTION_FILENAME
        ),
        api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME: sha256_file(
            run_dir / api.ASSET_ATTRIBUTION_CONSERVATION_FILENAME
        ),
    }
    assert manifest.product_checksums == expected
