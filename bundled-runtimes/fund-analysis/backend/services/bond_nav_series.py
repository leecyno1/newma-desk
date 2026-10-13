"""债基分析的净值口径：只用复权值，保留已知日期上的数据缺口。"""
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def positive_levels(rows: List[Dict[str, Any]], field: str = "adj_nav") -> pd.Series:
    values = {}
    for row in rows:
        raw_date = row.get("date") or row.get("trade_date")
        if raw_date is None:
            continue
        try:
            item_date = pd.Timestamp(str(raw_date)[:10])
        except ValueError:
            continue
        if pd.isna(item_date):
            continue
        try:
            value = float(row.get(field))
        except (TypeError, ValueError):
            value = np.nan
        # Do not drop the date: doing so would join returns across a known gap.
        values[item_date] = value if np.isfinite(value) and value > 0 else np.nan
    return pd.Series(values, index=pd.DatetimeIndex(list(values)), dtype=float).sort_index()


def weekly_endpoints(levels: pd.Series) -> pd.Series:
    """每周最后一个实际记录日期；数值缺失也不回退到较早一天。"""
    return pd.Series(levels.index, index=levels.index).resample("W-FRI").last()


def returns_at_endpoints(levels: pd.Series, endpoints: pd.Series) -> pd.Series:
    sampled = pd.Series(levels.reindex(pd.DatetimeIndex(endpoints)).to_numpy(), index=endpoints.index)
    return sampled.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()
