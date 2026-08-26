"""Fundamental asset-growth investment factor."""

from __future__ import annotations

import pandas as pd

from src.factors.base import zscore

__alpha_meta__ = {
    "id": "fund_asset_growth",
    "nickname": "Asset growth - inverse investment factor",
    "theme": ["growth"],
    "formula_latex": r"-\mathrm{zscore}_{x}(\Delta \mathrm{total\_assets}_{YoY})",
    "columns_required": ["fund:asset_growth"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "Inverse PIT-safe asset-growth factor. High asset growth is treated as "
        "aggressive investment and receives lower scores; low/negative growth "
        "receives higher scores."
    ),
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return negative cross-sectional z-scored asset growth."""
    return -zscore(panel["fund:asset_growth"])
