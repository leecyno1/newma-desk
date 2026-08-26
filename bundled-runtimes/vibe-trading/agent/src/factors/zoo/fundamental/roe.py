"""Fundamental ROE quality factor."""

from __future__ import annotations

import pandas as pd

from src.factors.base import zscore

__alpha_meta__ = {
    "id": "fund_roe",
    "nickname": "ROE - return on equity (PIT-safe fundamentals)",
    "theme": ["quality"],
    "formula_latex": r"\mathrm{zscore}_{x}(\mathrm{ROE})",
    "columns_required": ["fund:roe"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "PIT-safe return on equity from the fundamental panel; cross-sectional "
        "z-score per date. Missing statements remain NaN and are excluded from "
        "that date's cross-section."
    ),
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return cross-sectional z-scored ROE."""
    return zscore(panel["fund:roe"])
