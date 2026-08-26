"""Deterministic vintage selection for cycle response-surface inputs."""

from __future__ import annotations

import pandas as pd


_VINTAGE_ORDER = {
    "realtime": 0,
    "latest_historical": 1,
    "pseudo_vintage": 2,
}
_REQUIRED_COLUMNS = {"date", "cycle_id", "vintage"}


def select_preferred_cycle_vintage(cycles: pd.DataFrame) -> pd.DataFrame:
    """Keep one governed vintage per date and cycle using catalog priority."""

    if not isinstance(cycles, pd.DataFrame):
        raise TypeError("cycles must be a pandas DataFrame")
    missing = _REQUIRED_COLUMNS.difference(cycles.columns)
    if missing:
        raise ValueError(f"cycles is missing columns: {sorted(missing)}")
    if cycles.empty:
        return cycles.copy(deep=True)
    values = cycles.copy(deep=True)
    vintage_order = values["vintage"].map(_VINTAGE_ORDER)
    if vintage_order.isna().any():
        unknown = sorted(set(values.loc[vintage_order.isna(), "vintage"].astype(str)))
        raise ValueError(f"cycles contains unknown vintages: {unknown}")
    values["_vintage_order"] = vintage_order.astype("int64")
    return (
        values.sort_values(
            ["date", "cycle_id", "_vintage_order"],
            kind="mergesort",
        )
        .drop_duplicates(["date", "cycle_id"], keep="first")
        .drop(columns="_vintage_order")
        .reset_index(drop=True)
    )


def select_current_cycle_snapshot(cycles: pd.DataFrame) -> pd.DataFrame:
    """Select each cycle's latest date after deterministic vintage resolution."""

    preferred = select_preferred_cycle_vintage(cycles)
    if preferred.empty:
        return preferred
    return (
        preferred.sort_values(
            ["cycle_id", "date"],
            ascending=[True, False],
            kind="mergesort",
        )
        .drop_duplicates("cycle_id", keep="first")
        .sort_values("cycle_id", kind="mergesort")
        .reset_index(drop=True)
    )


__all__ = ["select_current_cycle_snapshot", "select_preferred_cycle_vintage"]
