"""Fundamental earnings-yield value factor."""

from __future__ import annotations

import pandas as pd

from src.factors.base import safe_div
from src.factors.base import zscore

__alpha_meta__ = {
    "id": "fund_earnings_yield",
    "nickname": "Earnings yield - net income over market cap",
    "theme": ["value"],
    "formula_latex": (
        r"\mathrm{zscore}_{x}\left("
        r"\frac{\mathrm{net\_income}}{\mathrm{close}\times\mathrm{shares\_diluted}}"
        r"\right)"
    ),
    "columns_required": ["close", "fund:net_income", "fund:shares_diluted"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "Hybrid value factor using PIT-safe net income and shares diluted "
        "aligned to the daily close panel. Division by zero/non-finite market "
        "cap becomes NaN before cross-sectional scoring."
    ),
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return cross-sectional z-scored earnings yield."""
    market_cap = panel["close"] * panel["fund:shares_diluted"]
    earnings_yield = safe_div(panel["fund:net_income"], market_cap)
    return zscore(earnings_yield)
