from __future__ import annotations

import math

import numpy as np
import pandas as pd

from scripts.research_track_forecast import build_track_forecast


def test_track_forecast_is_validated_dynamic_and_continuous() -> None:
    rng = np.random.default_rng(11)
    index = pd.period_range("1990-01", periods=420, freq="M")
    time = np.arange(len(index), dtype=float)
    c4 = pd.Series(np.sin(2.0 * math.pi * time / 42.0), index=index)
    series = pd.Series(
        1.15 * np.sin(2.0 * math.pi * (time - 4.0) / 42.0)
        + 0.18 * np.sin(2.0 * math.pi * time / 12.0)
        + rng.normal(0.0, 0.08, len(index)),
        index=index,
    )
    future = [
        {
            "date": str(index[-1] + horizon),
            "median": math.sin(2.0 * math.pi * (len(index) - 1 + horizon) / 42.0),
        }
        for horizon in range(1, 25)
    ]

    result = build_track_forecast(
        track_id="synthetic",
        series=series,
        c4_history=c4,
        c4_forecast=future,
        forecast_as_of=str(index[-1]),
    )

    assert result["status"] == "limited"
    assert result["bridge"]["date"] == str(index[-1])
    assert result["bridge"]["value"] == series.iloc[-1]
    assert len(result["dates"]) == 24
    assert len(set(round(value, 4) for value in result["median"])) > 12
    assert result["validation"]["qualifiedHorizons"] >= 2
    assert result["judgment"]["direction3"] in {"上行", "下行", "震荡"}


def test_track_forecast_blocks_short_history() -> None:
    index = pd.period_range("2020-01", periods=40, freq="M")
    series = pd.Series(np.linspace(-1.0, 1.0, len(index)), index=index)
    c4 = pd.Series(np.sin(np.arange(len(index))), index=index)
    future = [
        {"date": str(index[-1] + horizon), "median": 0.0}
        for horizon in range(1, 25)
    ]

    result = build_track_forecast(
        track_id="short",
        series=series,
        c4_history=c4,
        c4_forecast=future,
        forecast_as_of=str(index[-1]),
    )

    assert result["status"] == "blocked"
    assert result["dates"] == []


def test_track_forecast_blocks_stale_input_vintage() -> None:
    index = pd.period_range("2020-01", periods=69, freq="M")
    time = np.arange(len(index), dtype=float)
    series = pd.Series(np.sin(time / 4.0), index=index)
    c4 = pd.Series(np.sin(time / 5.0), index=index)
    future = [
        {"date": str(index[-1] + horizon), "median": 0.0}
        for horizon in range(1, 25)
    ]

    result = build_track_forecast(
        track_id="stale",
        series=series,
        c4_history=c4,
        c4_forecast=future,
        forecast_as_of="2026-06",
    )

    assert result["status"] == "blocked"
    assert result["dates"] == []
    assert result["inputLagMonths"] == 9
