from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.update_c4_realtime_bridge import DEFAULT_INPUT, build_bridge


def test_c4_realtime_bridge_extends_only_after_validated_cutoffs() -> None:
    payload = json.loads(DEFAULT_INPUT.read_text(encoding="utf-8"))
    timeline = pd.DataFrame(payload["timeline"])
    index = pd.PeriodIndex(timeline["date"], freq="M").to_timestamp("M")
    observed = pd.Series(timeline["observed"].to_numpy(), index=index, dtype=float)
    base = observed.interpolate(limit_direction="both")
    future_index = pd.date_range(index[-1] + pd.offsets.MonthEnd(1), periods=3, freq="ME")
    full_index = index.append(future_index)
    extended = base.reindex(full_index).ffill()
    features = pd.DataFrame(
        {
            "level": extended,
            "lag1": extended.shift(1).bfill(),
            "lag3": extended.shift(3).bfill(),
            "mean3": extended.rolling(3, min_periods=1).mean(),
            "slope3": extended.diff(3).fillna(0.0),
        },
        index=full_index,
    )

    bridged = build_bridge(payload, features, through="2026-03")

    assert bridged["bridge_validation"]["publishable_bridge"] is True
    assert bridged["bridge_validation"]["origins"] >= 8
    assert bridged["latest"]["date"] == "2026-03"
    assert len(bridged["timeline"]) == len(payload["timeline"]) + 3
    assert bridged["timeline"][-1]["observed_status"] == "indicator_family_bridge"
    assert bridged["latest"]["retro_publishable"] is False
