from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import math
from pathlib import Path

import pandas as pd

from seven_cycle_platform.storage import RunContext
from seven_cycle_platform.surfaces.materialize import (
    SurfaceRequest,
    build_and_write_cycle_asset_surfaces,
    materialize_cycle_asset_surfaces,
)


def _context() -> RunContext:
    return RunContext.create(
        as_of=date(2026, 6, 30),
        data_vintage=date(2026, 6, 30),
        model_version="surface-materialize-v1",
        config={"surface_schedule": "monthly"},
        input_checksums={"inputs/catalog": hashlib.sha256(b"catalog").hexdigest()},
        quality_summary={"surface": {"failed": 0, "passed": 1}},
        created_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )


def _inputs(sample_count: int = 60) -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2021-01-31", periods=sample_count, freq="ME")
    cycles: list[dict[str, object]] = []
    returns: list[dict[str, object]] = []
    for index, timestamp in enumerate(dates):
        angle_x = float((index * 31) % 360)
        angle_y = float((index * 47 + 40) % 360)
        cycles.extend(
            [
                {"date": timestamp.date(), "cycle_id": "C3", "angle": angle_x, "vintage": "latest_historical"},
                {"date": timestamp.date(), "cycle_id": "C5", "angle": angle_y, "vintage": "latest_historical"},
            ]
        )
        returns.append(
            {
                "asset_id": "gold",
                "period_end": timestamp.date(),
                "horizon_months": 12,
                "return_basis": "total_return",
                "component_type": "cycle",
                "component_id": "C3",
                "observed_return": 0.06 * math.sin(math.radians(angle_x))
                + 0.04 * math.cos(math.radians(angle_y)),
            }
        )
    return {
        "cycles": pd.DataFrame(cycles),
        "returns": pd.DataFrame(returns),
        "current_cycles": pd.DataFrame(
            [
                {"cycle_id": "C3", "angle": 130.0},
                {"cycle_id": "C5", "angle": 230.0},
            ]
        ),
        "forecasts": pd.DataFrame(
            [
                {"cycle_id": "C3", "horizon_months": 12, "status": "available", "angle_q50": 170.0},
                {"cycle_id": "C5", "horizon_months": 12, "status": "available", "angle_q50": 260.0},
            ]
        ),
        "current_mapping": pd.DataFrame(
            [{"asset_id": "gold", "horizon_months": 12, "absolute_expected_return": 0.05}]
        ),
        "future_mapping": pd.DataFrame(
            [
                {
                    "asset_id": "gold",
                    "horizon_months": 12,
                    "scenario_id": "baseline",
                    "status": "available",
                    "absolute_expected_return": 0.08,
                }
            ]
        ),
    }


def test_materialize_builds_governed_surface_product_with_future_path() -> None:
    inputs = _inputs()
    product = materialize_cycle_asset_surfaces(
        **inputs,
        requests=[
            SurfaceRequest(
                asset_id="gold",
                asset_label="黄金",
                cycle_x="C3",
                cycle_y="C5",
                horizon_months=12,
                scenario_id="baseline",
                window_months=60,
                grid_size=19,
            )
        ],
        context=_context(),
    )

    row = product.surfaces.iloc[0]
    assert row["status"] == "available"
    assert row["sample_count"] == 60
    assert '"label":"未来预测"' in row["future_path_json"]
    assert '"z":0.08' in row["future_path_json"]


def test_build_and_write_cycle_asset_surfaces_creates_scheduled_artifact(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    context = _context()
    run_dir = tmp_path / context.run_id
    run_dir.mkdir()

    path = build_and_write_cycle_asset_surfaces(
        run_dir,
        **inputs,
        requests=[
            SurfaceRequest(
                asset_id="gold",
                asset_label="黄金",
                cycle_x="C3",
                cycle_y="C5",
                horizon_months=12,
                scenario_id="baseline",
                window_months=60,
                grid_size=19,
            )
        ],
        context=context,
    )

    assert path.name == "cycle_asset_surface.parquet"
