from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from seven_cycle_platform.products.cycle_asset_surface import (
    CYCLE_ASSET_SURFACE_COLUMNS,
    CYCLE_ASSET_SURFACE_FILENAME,
    CYCLE_ASSET_SURFACE_SCHEMA,
    build_cycle_asset_surface_product,
    validate_cycle_asset_surface_product,
    write_cycle_asset_surface_product,
)
from seven_cycle_platform.storage import RunContext


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="surface-product-v1",
        config={"surface": "scheduled"},
        input_checksums={"catalog/source": hashlib.sha256(b"source").hexdigest()},
        quality_summary={"surface_checks": {"passed": 3, "failed": 0}},
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )


def _surface() -> dict[str, object]:
    return {
        "asset_id": "gold",
        "asset_label": "黄金",
        "cycle_x": "C3",
        "cycle_y": "C5",
        "metric": "observed_return",
        "estimator_version": "circular-kernel-loocv-v1",
        "horizon_months": 12,
        "scenario_id": "baseline",
        "window_months": 60,
        "grid_size": 19,
        "status": "available",
        "observations": [
            {
                "date": timestamp.date().isoformat(),
                "x": float((index * 31) % 360),
                "y": float((index * 47 + 40) % 360),
                "z": 0.04,
                "vintage": "latest_historical",
            }
            for index, timestamp in enumerate(
                pd.date_range(end="2026-05-31", periods=60, freq="ME")
            )
        ],
        "grid": [
            {
                "x": 0.0,
                "y": 0.0,
                "z": 0.01,
                "lower80": -0.02,
                "upper80": 0.04,
                "density": 4.0,
            }
        ],
        "current_point": {"x": 130.0, "y": 230.0, "z": 0.05},
        "future_path": [
            {"label": "当前", "x": 130.0, "y": 230.0, "z": 0.05},
            {"label": "未来预测", "x": 170.0, "y": 260.0, "z": 0.08},
        ],
        "evidence": {
            "sample_count": 60,
            "bandwidth": 0.25,
            "oos_score": 0.32,
            "identifiable": True,
            "reason": "样本量与留一法外样本检验通过",
        },
    }


def test_surface_product_schema_is_exact_and_stable() -> None:
    assert tuple(CYCLE_ASSET_SURFACE_SCHEMA.names) == CYCLE_ASSET_SURFACE_COLUMNS
    assert CYCLE_ASSET_SURFACE_FILENAME == "cycle_asset_surface.parquet"
    assert CYCLE_ASSET_SURFACE_COLUMNS[:6] == (
        "asset_id",
        "asset_label",
        "cycle_x",
        "cycle_y",
        "metric",
        "horizon_months",
    )


def test_surface_product_builds_canonical_json_and_provenance() -> None:
    context = _context()

    product = build_cycle_asset_surface_product([_surface()], context=context)
    validate_cycle_asset_surface_product(product, context=context)

    row = product.surfaces.iloc[0]
    assert row["run_id"] == context.run_id
    assert row["config_hash"] == context.config_hash
    assert json.loads(row["observations_json"])[-1]["date"] == "2026-05-31"
    assert json.loads(row["grid_json"])[0]["density"] == 4.0
    assert json.loads(row["future_path_json"])[-1]["label"] == "未来预测"
    assert row["identifiable"] is True or bool(row["identifiable"]) is True


def test_surface_product_writes_exact_schema_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    context = _context()
    run_dir = tmp_path / context.run_id
    run_dir.mkdir()
    product = build_cycle_asset_surface_product([_surface()], context=context)

    path = write_cycle_asset_surface_product(run_dir, product, context=context)

    assert path.name == CYCLE_ASSET_SURFACE_FILENAME
    assert pq.read_schema(path) == CYCLE_ASSET_SURFACE_SCHEMA
    frame = pq.read_table(path).to_pandas()
    assert frame.loc[0, "asset_id"] == "gold"
    with pytest.raises(FileExistsError, match="refuse accidental overwrite"):
        write_cycle_asset_surface_product(run_dir, product, context=context)


def test_surface_product_rejects_duplicate_dimensions() -> None:
    context = _context()
    surface = _surface()

    with pytest.raises(ValueError, match="duplicate surface dimensions"):
        build_cycle_asset_surface_product([surface, surface], context=context)


def test_surface_product_rejects_non_identifiable_grid() -> None:
    context = _context()
    surface = _surface()
    surface["status"] = "not_identifiable"
    surface["grid"] = [{"x": 0, "y": 0, "z": 0, "lower80": 0, "upper80": 0, "density": 1}]
    surface["evidence"] = {
        "sample_count": 60,
        "bandwidth": None,
        "oos_score": None,
        "identifiable": False,
        "reason": "样本不足",
    }

    with pytest.raises(ValueError, match="cannot contain a fitted grid"):
        build_cycle_asset_surface_product([surface], context=context)
