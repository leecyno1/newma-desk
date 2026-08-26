from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from seven_cycle_platform.legacy.research_surface_release import (
    build_forward_return_history,
    build_surface_requests,
    publish_research_surface_release,
)
from seven_cycle_platform.storage import RunContext, publish_run


def test_forward_return_history_uses_forward_compounding() -> None:
    panel = pd.DataFrame(
        {("A股宽基指数", "沪深300"): [0.10, -0.05, 0.20]},
        index=pd.date_range("2025-01-31", periods=3, freq="ME"),
    )
    panel.columns = pd.MultiIndex.from_tuples(panel.columns)

    result = build_forward_return_history(panel, horizons=(2,))

    assert result[["asset_id", "period_end", "horizon_months"]].to_dict("records") == [
        {
            "asset_id": "cn_equity_hs300",
            "period_end": pd.Timestamp("2025-01-31").date(),
            "horizon_months": 2,
        },
        {
            "asset_id": "cn_equity_hs300",
            "period_end": pd.Timestamp("2025-02-28").date(),
            "horizon_months": 2,
        },
    ]
    assert result["observed_return"].tolist() == pytest.approx([0.045, 0.14])


def test_surface_requests_cover_every_distinct_cycle_pair() -> None:
    requests = build_surface_requests(
        asset_labels={"cn_equity_hs300": "沪深300", "us_equity_sp500": "标普500"},
        horizons=(3, 12),
        window_months=60,
        grid_size=19,
    )

    assert len(requests) == 2 * 2 * 21
    assert all(request.cycle_x != request.cycle_y for request in requests)
    assert {request.horizon_months for request in requests} == {3, 12}


def test_surface_requests_can_materialize_all_supported_windows() -> None:
    requests = build_surface_requests(
        asset_labels={"cn_equity_hs300": "沪深300"},
        horizons=(6,),
        window_months=(48, 60, 120),
        grid_size=27,
    )

    assert len(requests) == 3 * 21
    assert {request.window_months for request in requests} == {48, 60, 120}


def test_research_release_publishes_all_assets_horizons_windows_and_pairs(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_context = RunContext.create(
        as_of=date(2025, 12, 31),
        data_vintage=date(2025, 12, 15),
        model_version="test-cycle-v1",
        config={"fixture": "three-window-release"},
        input_checksums={"fixture": "0" * 64},
        quality_summary={"vintage_status": "retrospective_only"},
        created_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
    )
    states = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2025-01-31"),
                "cycle_id": f"C{cycle_number}",
                "vintage": "pseudo_vintage",
                "vintage_caveat": "test fixture without release vintages",
                "angle": float(cycle_number * 30),
                "phase": "expansion",
                "level": 1.0,
                "slope": 0.1,
                "amplitude": 1.0,
                "uncertainty": 0.1,
                "center_period": float(cycle_number * 12),
                "bandwidth": 0.2,
                "confidence": 0.8,
            }
            for cycle_number in range(1, 8)
        ]
    )

    def write_source(staging_dir: Path) -> None:
        states.to_parquet(staging_dir / "cycle_phase_vintage.parquet", index=False)

    source_manifest = publish_run(
        source_root,
        source_context,
        write_staging=write_source,
    )
    returns = pd.DataFrame(
        0.01,
        index=pd.date_range("2025-01-31", periods=12, freq="ME"),
        columns=pd.MultiIndex.from_tuples(
            [
                ("A股宽基指数", "沪深300"),
                ("A股宽基指数", "中证500"),
                ("A股宽基指数", "中证1000"),
                ("各类债券指数", "国债指数(上证)"),
                ("海外指数/ETF", "标普500(SPY)"),
            ]
        ),
    )
    returns_path = tmp_path / "returns.parquet"
    returns.to_parquet(returns_path)

    result = publish_research_surface_release(
        source_cycle_run=source_root / "runs" / source_manifest.run_id,
        returns_path=returns_path,
        product_root=tmp_path / "research",
        horizons=(3, 6, 12),
        window_months=(48, 60, 120),
        grid_size=9,
    )
    published = pd.read_parquet(result.run_dir / "cycle_asset_surface.parquet")

    assert result.surface_count == 945
    assert len(published) == 945
    assert published["asset_id"].nunique() == 5
    assert set(published["horizon_months"]) == {3, 6, 12}
    assert set(published["window_months"]) == {48, 60, 120}
    assert published[["cycle_x", "cycle_y"]].drop_duplicates().shape[0] == 21
