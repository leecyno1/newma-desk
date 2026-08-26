from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research_c2_regime_refactor import (
    _annual_forward_path_values,
    _annual_forward_target_values,
)


def test_c2_forward_risk_counts_only_negative_returns() -> None:
    asset = pd.DataFrame(
        {
            "year": [2000, 2001, 2002, 2003],
            "return": [0.0, 0.25, -0.12, 0.08],
        }
    )

    one_year = _annual_forward_target_values(
        asset,
        horizon_years=1,
        target="risk",
    )

    assert one_year[2000] == 0.0
    assert one_year[2001] == 0.12
    assert one_year[2002] == 0.0


def test_c2_asset_class_targets_separate_drawdown_and_rate_shock() -> None:
    asset = pd.DataFrame(
        {
            "year": [2000, 2001, 2002, 2003],
            "return": [0.02, 0.10, -0.20, 0.05],
        }
    )

    targets = _annual_forward_path_values(asset, horizon_years=2)

    assert targets["forwardReturn"][2000] == pytest.approx(-0.12)
    assert targets["forwardMaxDrawdown"][2000] == pytest.approx(0.20)
    assert targets["forwardRateShock"][2000] == pytest.approx(0.30)
