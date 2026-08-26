from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.refresh_asset_returns_current import (
    _merge_returns,
    _monthly_returns,
    _parse_ken_french_17_monthly,
)


def test_monthly_returns_uses_month_end_levels() -> None:
    level = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(["2025-01-15", "2025-02-14", "2025-03-20"]),
    )

    result = _monthly_returns(level)

    assert result.loc[pd.Timestamp("2025-02-28")] == pytest.approx(0.10)
    assert result.loc[pd.Timestamp("2025-03-31")] == pytest.approx(0.10)


def test_merge_returns_preserves_existing_history() -> None:
    columns = pd.MultiIndex.from_tuples([("category", "asset")])
    frame = pd.DataFrame(
        [0.01, 0.02],
        index=pd.to_datetime(["2025-01-31", "2025-02-28"]),
        columns=columns,
    )
    update = pd.Series(
        [0.03, 0.04],
        index=pd.to_datetime(["2025-02-28", "2025-03-31"]),
    )

    result = _merge_returns(
        frame,
        ("category", "asset"),
        update,
        start=pd.Timestamp("2025-02-28"),
        through=pd.Timestamp("2025-03-31"),
    )

    assert result.loc[pd.Timestamp("2025-01-31"), ("category", "asset")] == 0.01
    assert result.loc[pd.Timestamp("2025-02-28"), ("category", "asset")] == 0.03
    assert result.loc[pd.Timestamp("2025-03-31"), ("category", "asset")] == 0.04


def test_refresh_specs_include_missing_commodity_and_fx_assets() -> None:
    from scripts.refresh_asset_returns_current import (
        GLOBAL_YAHOO_SPECS,
        LOCAL_PANEL_SPECS,
    )

    assert GLOBAL_YAHOO_SPECS[("商品", "黄金")] == "GC=F"
    assert GLOBAL_YAHOO_SPECS[("商品", "铜")] == "HG=F"
    assert GLOBAL_YAHOO_SPECS[("商品", "原油")] == "CL=F"
    assert GLOBAL_YAHOO_SPECS[("外汇", "美元指数DXY")] == "DX-Y.NYB"
    assert LOCAL_PANEL_SPECS[("商品", "中国大宗商品价格综合指数")]


def test_parse_ken_french_17_monthly_uses_value_weighted_monthly_section() -> None:
    text = """Header
  Average Value Weighted Returns -- Monthly
,Food,Mines
202601, 1.50, -2.00
202602, -99.99, 3.25

  Average Equal Weighted Returns -- Monthly
,Food,Mines
202601, 9.00, 9.00
"""

    result = _parse_ken_french_17_monthly(text)

    assert result.loc[pd.Timestamp("2026-01-31"), "Food"] == pytest.approx(0.015)
    assert pd.isna(result.loc[pd.Timestamp("2026-02-28"), "Food"])
    assert result.loc[pd.Timestamp("2026-02-28"), "Mines"] == pytest.approx(0.0325)
