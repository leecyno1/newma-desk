from __future__ import annotations

import math

import numpy as np
import pandas as pd

from seven_cycle_platform.surfaces.response import build_cycle_asset_surface


def _fixtures(sample_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2018-01-31", periods=sample_count, freq="ME")
    cycle_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    for index, date in enumerate(dates):
        angle_x = float((index * 31) % 360)
        angle_y = float((index * 47 + 40) % 360)
        cycle_rows.extend(
            [
                {
                    "date": date.date(),
                    "cycle_id": "C3",
                    "angle": angle_x,
                    "vintage": "latest_historical",
                },
                {
                    "date": date.date(),
                    "cycle_id": "C5",
                    "angle": angle_y,
                    "vintage": "latest_historical",
                },
            ]
        )
        return_rows.append(
            {
                "period_end": date.date(),
                "observed_return": 0.06 * math.sin(math.radians(angle_x))
                + 0.04 * math.cos(math.radians(angle_y)),
                "return_basis": "total_return",
                "component_type": "cycle",
                "component_id": "C3",
            }
        )
    return pd.DataFrame(cycle_rows), pd.DataFrame(return_rows)


def test_surface_is_published_only_after_sample_and_oos_gates() -> None:
    cycles, returns = _fixtures(72)

    result = build_cycle_asset_surface(
        cycles=cycles,
        returns=returns,
        asset_id="gold",
        asset_label="黄金",
        cycle_x="C3",
        cycle_y="C5",
        grid_size=19,
    )

    assert result["status"] == "available"
    assert result["evidence"]["sample_count"] == 72
    assert result["evidence"]["oos_score"] > 0
    assert len(result["observations"]) == 72
    assert len(result["grid"]) == 19 * 19


def test_surface_keeps_observations_but_withholds_grid_when_not_identifiable() -> None:
    cycles, returns = _fixtures(18)

    result = build_cycle_asset_surface(
        cycles=cycles,
        returns=returns,
        asset_id="gold",
        asset_label="黄金",
        cycle_x="C3",
        cycle_y="C5",
    )

    assert result["status"] == "not_identifiable"
    assert result["grid"] == []
    assert len(result["observations"]) == 18
    assert "至少 36" in result["evidence"]["reason"]


def test_duplicate_attribution_components_count_one_return_per_date() -> None:
    cycles, returns = _fixtures(40)
    duplicated = pd.concat(
        [
            returns,
            returns.assign(component_id="C5"),
            returns.assign(component_type="channel", component_id="growth"),
        ],
        ignore_index=True,
    )

    result = build_cycle_asset_surface(
        cycles=cycles,
        returns=duplicated,
        asset_id="gold",
        asset_label="黄金",
        cycle_x="C3",
        cycle_y="C5",
    )

    assert len(result["observations"]) == 40
    assert len({point["date"] for point in result["observations"]}) == 40


def test_multi_month_oos_gate_purges_overlapping_return_windows() -> None:
    dates = pd.date_range("2015-01-31", periods=120, freq="ME")
    random = np.random.default_rng(20260715)
    monthly_returns = pd.Series(random.normal(0.0, 0.04, len(dates)), index=dates)
    forward_returns = (
        monthly_returns.add(1.0)
        .rolling(12)
        .apply(np.prod, raw=True)
        .shift(-11)
        .sub(1.0)
    )
    cycle_rows: list[dict[str, object]] = []
    for index, timestamp in enumerate(dates):
        cycle_rows.extend(
            [
                {
                    "date": timestamp.date(),
                    "cycle_id": "C3",
                    "angle": float((index * 3) % 360),
                    "vintage": "pseudo_vintage",
                },
                {
                    "date": timestamp.date(),
                    "cycle_id": "C5",
                    "angle": float((index * 7 + 20) % 360),
                    "vintage": "pseudo_vintage",
                },
            ]
        )
    returns = forward_returns.dropna().rename("observed_return").reset_index()
    returns.columns = ["period_end", "observed_return"]
    returns["period_end"] = returns["period_end"].dt.date

    result = build_cycle_asset_surface(
        cycles=pd.DataFrame(cycle_rows),
        returns=returns,
        asset_id="cn_equity_hs300",
        asset_label="沪深300",
        cycle_x="C3",
        cycle_y="C5",
        horizon_months=12,
    )

    assert result["status"] == "not_identifiable"
    assert "净化交叠样本" in result["evidence"]["reason"]
