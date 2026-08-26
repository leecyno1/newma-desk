from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_c7_risk_appetite_state import (
    OUTPUT_PATH,
    _feature_frame,
)

import pandas as pd


def test_c7_risk_appetite_state_preserves_publication_gates() -> None:
    assert OUTPUT_PATH.exists()
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload["status"] == "short_horizon_regime_predictable"
    assert payload["publicationStatus"] == "limited"
    assert payload["governance"]["formalCycleStatus"] == "blocked"
    assert payload["governance"]["assetForecastStatus"] == "blocked"
    assert payload["validation"]["1m"]["qualified"] is True
    assert payload["validation"]["3m"]["qualified"] is True
    assert payload["validation"]["6m"]["qualified"] is False
    assert payload["pathValidation"]["5m"]["qualified"] is True
    assert len(payload["forecastPath"]) == 6
    assert len({row["scenarioLevel"] for row in payload["forecastPath"]}) > 2
    assert payload["validation"]["1m"]["accuracy"] >= 0.65
    assert payload["validation"]["1m"]["auc"] >= 0.70
    assert payload["validation"]["3m"]["accuracy"] >= 0.65
    assert payload["validation"]["3m"]["auc"] >= 0.68
    assert payload["assetValidation"]["status"] == "blocked"
    assert payload["assetValidation"]["summary"]["assetGroups"] == 5
    assert payload["assetValidation"]["summary"]["horizons"] == [1, 3, 6]
    assert payload["assetValidation"]["summary"]["totalChannels"] == 30
    assert len(payload["assetValidation"]["cells"]) == 15
    assert {cell["assetGroup"] for cell in payload["assetValidation"]["cells"]} == {
        "中国股票",
        "海外股票",
        "债券",
        "商品",
        "外汇",
    }
    assert all(
        cell["volatility"]["observations"] >= 72
        for cell in payload["assetValidation"]["cells"]
        if cell["horizonMonths"] == 1
    )
    assert payload["current"]["date"] == payload["meta"]["asOf"]
    assert payload["current"]["date"] == payload["timeline"][-1]["date"]
    assert payload["current"]["date"] >= "2026-06"
    assert len(payload["timeline"]) > 250
    assert {row["family"] for row in payload["familyCoverage"]} == {
        "市场收益",
        "风格偏好",
        "交易活跃",
        "融资拥挤",
        "外部避险",
        "波动信用压力",
    }


def test_c7_features_use_current_month_state() -> None:
    index = pd.date_range("2025-01-31", periods=8, freq="ME")
    state = pd.Series(range(8), index=index, dtype=float)
    families = pd.DataFrame({"市场收益": state, "交易活跃": state}, index=index)

    features = _feature_frame(families, state)

    assert features.loc[index[-1], "state"] == state.loc[index[-1]]
    assert features.loc[index[-1], "lag_1"] == state.loc[index[-2]]
