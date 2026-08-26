from __future__ import annotations

from pathlib import Path

import pandas as pd

from seven_cycle_platform.assets.c2_exposure import (
    build_c2_asset_exposure_registry,
    build_weighted_c2_features,
)


ROOT = Path(__file__).resolve().parents[3]


def test_c2_exposure_uses_underlying_market_not_listing_market() -> None:
    registry = build_c2_asset_exposure_registry(
        [
            ("A股宽基指数", "沪深300"),
            ("海外指数/ETF", "标普500(SPY)"),
            ("海外指数/ETF", "德国ETF(EWG)"),
            ("商品", "黄金"),
        ],
        ROOT / "config" / "seven_cycle" / "c2_asset_exposures.yaml",
    ).set_index("assetId")

    assert registry.loc["A股宽基指数||沪深300", "c2Weights"] == {"CHN": 1.0}
    assert registry.loc["海外指数/ETF||标普500(SPY)", "c2Weights"] == {
        "USA": 1.0
    }
    assert registry.loc["海外指数/ETF||德国ETF(EWG)", "listingMarket"] == "US"
    assert registry.loc["海外指数/ETF||德国ETF(EWG)", "underlyingMarket"] == "DE"
    assert registry.loc["海外指数/ETF||德国ETF(EWG)", "c2Weights"] == {
        "GLOBAL": 1.0
    }
    assert registry.loc["商品||黄金", "c2Weights"] == {"GLOBAL": 1.0}


def test_weighted_c2_features_preserve_registered_weights() -> None:
    index = pd.date_range("2020-01-31", periods=3, freq="ME")
    tracks = {
        "GLOBAL": pd.DataFrame({"C2": [0.0, 0.1, 0.2]}, index=index),
        "USA": pd.DataFrame({"C2": [1.0, 1.1, 1.2]}, index=index),
    }

    weighted = build_weighted_c2_features(
        tracks,
        {"GLOBAL": 0.25, "USA": 0.75},
    )

    expected = pd.DataFrame({"C2": [0.75, 0.85, 0.95]}, index=index)
    pd.testing.assert_frame_equal(weighted, expected)
