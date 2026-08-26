"""Fundamental gross-profitability quality factor."""

from __future__ import annotations

import pandas as pd

from src.factors.base import zscore

__alpha_meta__ = {
    "id": "fund_gross_profitability",
    "nickname": "Gross profitability - gross profit over total assets",
    "theme": ["quality"],
    "formula_latex": r"\mathrm{zscore}_{x}(\mathrm{gross\_profit}/\mathrm{total\_assets})",
    "columns_required": ["fund:gross_profitability"],
    "universe": ["equity_us", "equity_cn", "equity_hk"],
    "frequency": ["1d"],
    "decay_horizon": 252,
    "min_warmup_bars": 1,
    "notes": (
        "PIT-safe Novy-Marx style gross profitability from the fundamental "
        "panel; cross-sectional z-score per date with missing issuers excluded."
    ),
}


def compute(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return cross-sectional z-scored gross profitability."""
    return zscore(panel["fund:gross_profitability"])
