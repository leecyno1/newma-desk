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
from seven_cycle_platform.types import VintageKind


CYCLE_IDS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
STATE_FIELDS = [
    "angle",
    "phase",
    "level",
    "slope",
    "amplitude",
    "uncertainty",
    "center_period",
    "bandwidth",
    "confidence",
]
COMMON_PROVENANCE_FIELDS = [
    "run_id",
    "as_of",
    "data_vintage",
    "model_version",
    "config_hash",
    "created_at",
]
EXPECTED_COLUMNS = [
    "date",
    "cycle_id",
    "vintage",
    "vintage_caveat",
    *STATE_FIELDS,
    *COMMON_PROVENANCE_FIELDS,
]


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2024, 6, 30),
        data_vintage=date(2024, 6, 30),
        model_version="seven-cycle-v1",
        config={"cycles": CYCLE_IDS, "strict_vintage": True},
        input_checksums={"observations.parquet": _checksum(b"observations")},
        quality_summary={"failed": 0, "passed": 2},
        created_at=datetime(2026, 7, 12, 9, 30, tzinfo=timezone.utc),
    )


def _state_frame(
    vintage: VintageKind,
    *,
    offset: float = 0.0,
    caveat: str | None = None,
) -> pd.DataFrame:
    centers = [45.0, 14.0, 9.0, 42.0, 21.0, 12.0, 6.0]
    bandwidths = [30.0, 8.0, 4.0, 24.0, 15.0, 9.0, 6.0]
    phases = [
        "expansion",
        "downturn",
        "contraction",
        "recovery",
        "expansion",
        "downturn",
        "recovery",
    ]
    rows = []
    for position, cycle_id in enumerate(CYCLE_IDS, start=1):
        phase = phases[position - 1]
        level = 0.10 * position + offset
        slope = 0.01 * position + offset
        if phase in {"contraction", "recovery"}:
            level = -level
        if phase in {"downturn", "contraction"}:
            slope = -slope
        rows.append(
            {
                "date": datetime(2024, 6, 30, 18, 45),
                "cycle_id": cycle_id,
                "vintage": vintage.value,
                "vintage_caveat": caveat,
                "angle": float((position * 37) % 360) + offset,
                "phase": phase,
                "level": level,
                "slope": slope,
                "amplitude": 0.20 * position + abs(offset),
                "uncertainty": 0.05 * position,
                "center_period": centers[position - 1],
                "bandwidth": bandwidths[position - 1],
                "confidence": 0.50 + 0.04 * position,
                "acceleration": 999.0,
                "innovation": 999.0,
                "frequency": "A" if position <= 3 else "M",
                "evidence_level": "high",
                "usage_status": "formal",
                "effective_cycles": 3.0,
                "observed_observations": 100,
                "member_breadth": 1.0,
                "category_breadth": 1.0,
                "total_members": 3,
                "total_categories": 3,
            }
        )
    return pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)


def test_cycle_phase_arrow_schema_is_stable_and_approved() -> None:
    from seven_cycle_platform.contracts.arrow import CYCLE_PHASE_VINTAGE_SCHEMA

    expected_types = {
        "date": pa.date32(),
        "cycle_id": pa.string(),
        "vintage": pa.string(),
        "vintage_caveat": pa.string(),
        "angle": pa.float64(),
        "phase": pa.string(),
        "level": pa.float64(),
        "slope": pa.float64(),
        "amplitude": pa.float64(),
        "uncertainty": pa.float64(),
        "center_period": pa.float64(),
        "bandwidth": pa.float64(),
        "confidence": pa.float64(),
        "run_id": pa.string(),
        "as_of": pa.date32(),
        "data_vintage": pa.date32(),
        "model_version": pa.string(),
        "config_hash": pa.string(),
        "created_at": pa.timestamp("us", tz="UTC"),
    }

    assert CYCLE_PHASE_VINTAGE_SCHEMA.names == EXPECTED_COLUMNS
    assert {
        field.name: field.type for field in CYCLE_PHASE_VINTAGE_SCHEMA
    } == expected_types


def test_product_dimension_is_date_cycle_id_vintage_with_context_provenance() -> None:
    from seven_cycle_platform.products.cycle_phase import (
        build_cycle_phase_vintage,
        validate_cycle_phase_vintage,
    )

    context = _context()
    realtime = _state_frame(VintageKind.REALTIME)
    latest = _state_frame(VintageKind.LATEST_HISTORICAL, offset=0.125)
    realtime_before = realtime.copy(deep=True)
    latest_before = latest.copy(deep=True)

    product = build_cycle_phase_vintage([latest, realtime], context=context)
    repeated = build_cycle_phase_vintage([latest, realtime], context=context)

    pd.testing.assert_frame_equal(realtime, realtime_before, check_exact=True)
    pd.testing.assert_frame_equal(latest, latest_before, check_exact=True)
    pd.testing.assert_frame_equal(product, repeated, check_exact=True)
    assert list(product.columns) == EXPECTED_COLUMNS
    assert len(product) == 14
    assert not product.duplicated(["date", "cycle_id", "vintage"]).any()
    assert product.groupby(["date", "vintage"]).size().tolist() == [7, 7]
    assert set(product["vintage"]) == {
        VintageKind.REALTIME.value,
        VintageKind.LATEST_HISTORICAL.value,
    }
    assert product.groupby("vintage")["angle"].first().nunique() == 2
    assert product["date"].eq(pd.Timestamp("2024-06-30")).all()
    assert product["run_id"].eq(context.run_id).all()
    assert product["as_of"].eq(context.as_of).all()
    assert product["data_vintage"].eq(context.data_vintage).all()
    assert product["model_version"].eq(context.model_version).all()
    assert product["config_hash"].eq(context.config_hash).all()
    assert product["created_at"].eq(context.created_at).all()
    assert "acceleration" not in product
    assert "innovation" not in product
    assert "usage_status" not in product
    validate_cycle_phase_vintage(product, context=context)


def test_pseudo_product_rows_keep_an_explicit_label_and_caveat() -> None:
    from seven_cycle_platform.products.cycle_phase import build_cycle_phase_vintage

    pseudo = _state_frame(
        VintageKind.PSEUDO_VINTAGE,
        caveat=(
            "Synthetic release timing; this is pseudo-vintage evidence, "
            "not true realtime history."
        ),
    )
    product = build_cycle_phase_vintage(pseudo, context=_context())

    assert set(product["vintage"]) == {VintageKind.PSEUDO_VINTAGE.value}
    assert product["vintage_caveat"].notna().all()
    assert product["vintage_caveat"].str.contains(
        "pseudo-vintage",
        case=False,
    ).all()

    missing_caveat = pseudo.copy(deep=True)
    missing_caveat["vintage_caveat"] = None
    with pytest.raises(ValueError, match="pseudo_vintage.*caveat"):
        build_cycle_phase_vintage(missing_caveat, context=_context())


@pytest.mark.parametrize(
    "vintage",
    [VintageKind.EXPLICIT_PROXY, VintageKind.UNAVAILABLE],
)
def test_cycle_phase_product_rejects_data_identity_vintages(
    vintage: VintageKind,
) -> None:
    from seven_cycle_platform.products.cycle_phase import build_cycle_phase_vintage

    with pytest.raises(
        ValueError,
        match=rf"cycle_phase_vintage product.*{vintage.value}",
    ):
        build_cycle_phase_vintage(_state_frame(vintage), context=_context())


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        (lambda frame: frame.assign(date=True), "date.*boolean"),
        (lambda frame: frame.assign(angle=True), "angle.*real"),
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "date.*cycle_id.*vintage.*unique",
        ),
        (
            lambda frame: frame.drop(index=frame.index[-1]),
            "exactly C1 through C7",
        ),
        (
            lambda frame: frame.assign(unexpected="not governed"),
            "unexpected state columns",
        ),
    ],
)
def test_product_builder_rejects_malformed_state_frames(
    mutation,
    expected_message: str,
) -> None:
    from seven_cycle_platform.products.cycle_phase import build_cycle_phase_vintage

    frame = mutation(_state_frame(VintageKind.REALTIME))

    with pytest.raises((TypeError, ValueError), match=expected_message):
        build_cycle_phase_vintage(frame, context=_context())


def test_product_builder_rejects_unaligned_missing_state_fields() -> None:
    from seven_cycle_platform.products.cycle_phase import build_cycle_phase_vintage

    frame = _state_frame(VintageKind.REALTIME)
    frame.loc[0, "level"] = np.nan

    with pytest.raises(ValueError, match="state missingness must align"):
        build_cycle_phase_vintage(frame, context=_context())


def test_run_context_is_the_only_allowed_provenance_source() -> None:
    from seven_cycle_platform.products.cycle_phase import build_cycle_phase_vintage

    frame = _state_frame(VintageKind.REALTIME)
    frame["run_id"] = "caller-controlled"

    with pytest.raises(ValueError, match="provenance.*RunContext"):
        build_cycle_phase_vintage(frame, context=_context())


def test_writer_refuses_overwrite_and_is_byte_deterministic(tmp_path: Path) -> None:
    from seven_cycle_platform.products.cycle_phase import (
        CYCLE_PHASE_VINTAGE_FILENAME,
        build_cycle_phase_vintage,
        write_cycle_phase_vintage,
    )

    context = _context()
    prior_realtime = _state_frame(VintageKind.REALTIME)
    prior_realtime["date"] = datetime(2024, 5, 31, 21, 15)
    prior_latest = _state_frame(
        VintageKind.LATEST_HISTORICAL,
        offset=0.125,
    )
    prior_latest["date"] = datetime(2024, 5, 31, 21, 15)
    product = build_cycle_phase_vintage(
        [
            _state_frame(VintageKind.REALTIME),
            _state_frame(VintageKind.LATEST_HISTORICAL, offset=0.125),
            prior_realtime,
            prior_latest,
        ],
        context=context,
    )
    shuffled = product.sample(frac=1.0, random_state=17).reset_index(drop=True)
    shuffled_before = shuffled.copy(deep=True)
    first_run_dir = tmp_path / "first" / context.run_id
    second_run_dir = tmp_path / "second" / context.run_id
    first_run_dir.mkdir(parents=True)
    second_run_dir.mkdir(parents=True)

    first_path = write_cycle_phase_vintage(
        first_run_dir,
        product,
        context=context,
    )
    second_path = write_cycle_phase_vintage(
        second_run_dir,
        shuffled,
        context=context,
    )

    pd.testing.assert_frame_equal(shuffled, shuffled_before, check_exact=True)
    assert first_path == first_run_dir / CYCLE_PHASE_VINTAGE_FILENAME
    assert first_path.read_bytes() == second_path.read_bytes()
    persisted = pd.read_parquet(second_path)
    persisted_keys = persisted.loc[:, ["date", "vintage", "cycle_id"]].copy()
    expected_keys = product.loc[:, ["date", "vintage", "cycle_id"]].copy()
    persisted_keys["date"] = pd.to_datetime(persisted_keys["date"])
    expected_keys["date"] = pd.to_datetime(expected_keys["date"])
    pd.testing.assert_frame_equal(
        persisted_keys,
        expected_keys,
        check_exact=True,
    )
    with pytest.raises(FileExistsError, match="refuse.*overwrite"):
        write_cycle_phase_vintage(first_run_dir, product, context=context)


def test_atomic_publish_manifest_contains_the_cycle_product_checksum(
    tmp_path: Path,
) -> None:
    from seven_cycle_platform.contracts.arrow import CYCLE_PHASE_VINTAGE_SCHEMA
    from seven_cycle_platform.products.cycle_phase import (
        CYCLE_PHASE_VINTAGE_FILENAME,
        build_cycle_phase_vintage,
        validate_cycle_phase_vintage,
        write_cycle_phase_vintage,
    )
    from seven_cycle_platform.storage import RunManifest

    context = _context()
    product = build_cycle_phase_vintage(
        [
            _state_frame(VintageKind.REALTIME),
            _state_frame(VintageKind.LATEST_HISTORICAL, offset=0.125),
        ],
        context=context,
    )
    product_root = tmp_path / "products" / "seven_cycle"

    def write_staging(staging_dir: Path) -> None:
        written = write_cycle_phase_vintage(
            staging_dir,
            product,
            context=context,
        )
        assert written.parent == staging_dir

    def validate_staging(staging_dir: Path, manifest: RunManifest) -> None:
        staged_path = staging_dir / CYCLE_PHASE_VINTAGE_FILENAME
        assert staged_path.is_file()
        assert manifest.product_checksums[CYCLE_PHASE_VINTAGE_FILENAME] == (
            sha256_file(staged_path)
        )
        assert pq.read_table(staged_path).schema == CYCLE_PHASE_VINTAGE_SCHEMA
        validate_cycle_phase_vintage(
            pd.read_parquet(staged_path),
            context=context,
        )

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
        validate_staging=validate_staging,
    )

    run_dir = product_root / "runs" / context.run_id
    published_path = run_dir / CYCLE_PHASE_VINTAGE_FILENAME
    assert published_path.is_file()
    assert published_path.parent == run_dir
    assert manifest.product_checksums == {
        CYCLE_PHASE_VINTAGE_FILENAME: sha256_file(published_path)
    }
    assert pq.read_table(published_path).schema == CYCLE_PHASE_VINTAGE_SCHEMA
