from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.refresh_c4_asset_statistics import (
    PHASES,
    _regression_statistics,
    build_asset_statistics,
    phase_from_angle,
)


@pytest.mark.parametrize(
    ("angle", "phase"),
    [(0, "recovery"), (90, "expansion"), (180, "downturn"), (270, "contraction")],
)
def test_phase_from_angle_uses_approved_quadrants(angle: float, phase: str) -> None:
    assert phase_from_angle(angle) == phase


def test_regression_uses_lagged_standardized_c4_features() -> None:
    index = pd.date_range("2005-01-31", periods=180, freq="ME")
    factor = pd.Series(np.sin(np.arange(180) / 7.0), index=index)
    level = factor.shift(1)
    slope = factor.diff(3).shift(1)
    asset_return = 0.002 + 0.01 * level - 0.006 * slope
    frame = pd.DataFrame({"return": asset_return, "factor": factor}).dropna()

    result = _regression_statistics(frame)

    assert result["in_sample_r2"] > 0.99
    assert result["impact_bps_per_1sigma"] > 0
    assert result["oos_folds"] > 0


def test_asset_statistics_preserve_all_four_phases() -> None:
    index = pd.date_range("2010-01-31", periods=120, freq="ME")
    phases = [PHASES[index % 4] for index in range(120)]
    state = pd.DataFrame(
        {
            "factor": np.sin(np.arange(120) / 6.0),
            "phase": phases,
            "cycle_identity": "latest_historical",
        },
        index=index,
    )
    returns = pd.DataFrame(
        {("商品", "黄金"): np.linspace(-0.02, 0.03, 120)},
        index=index,
    )
    returns.columns = pd.MultiIndex.from_tuples(returns.columns)

    payload = build_asset_statistics(returns, state)

    assert payload["summary"]["total_rows"] == 1
    assert set(payload["assets"][0]["phase_stats"]) == set(PHASES)
    assert payload["assets"][0]["end"] == "2019-12"
