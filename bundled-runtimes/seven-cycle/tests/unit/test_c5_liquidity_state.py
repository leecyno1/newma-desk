from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_c5_liquidity_state import (
    OUTPUT_PATH,
    _asset_classifier,
    _segmented_ewm,
)


def test_c5_smoothing_resets_after_missing_months() -> None:
    series = pd.Series(
        [1.0, 1.2, 1.4, np.nan, 2.0, 2.2, 2.4],
        index=pd.date_range("2025-01-31", periods=7, freq="ME"),
    )

    smoothed = _segmented_ewm(series, span=3, min_periods=2)

    assert pd.isna(smoothed.iloc[3])
    assert pd.isna(smoothed.iloc[4])
    assert smoothed.iloc[5] > 2.0


def test_asset_classifier_averages_regularization_models() -> None:
    features = pd.DataFrame(
        {"signal": [-2.0, -1.0, 1.0, 2.0]},
    )
    target = pd.Series([0, 0, 1, 1])
    classifier = _asset_classifier((0.01, 0.05))

    classifier.fit(features, target)
    probabilities = classifier.predict_proba(pd.DataFrame({"signal": [0.5]}))

    assert probabilities.shape == (1, 2)
    assert 0.0 < probabilities[0, 1] < 1.0


def test_c5_liquidity_state_preserves_publication_gates() -> None:
    assert OUTPUT_PATH.exists()
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload["status"] == "state_direction_predictable"
    assert payload["publicationStatus"] == "limited"
    assert payload["governance"]["formalCycleStatus"] == "blocked"
    assert payload["governance"]["assetForecastStatus"] == "blocked"
    assert payload["validation"]["3m"]["qualified"] is True
    assert payload["validation"]["6m"]["qualified"] is True
    assert payload["validation"]["12m"]["qualified"] is True
    assert (
        payload["validation"]["3m"]["brier"]
        < payload["validation"]["3m"]["momentumBrier"]
    )
    assert payload["validation"]["6m"]["accuracy"] >= 0.60
    assert payload["validation"]["12m"]["auc"] >= 0.65
    assert payload["assetValidation"]["status"] == "blocked"
    assert payload["assetValidation"]["summary"]["totalChannels"] == 30
    assert payload["assetValidation"]["summary"]["returnChannelsPassed"] == 1
    assert payload["assetValidation"]["summary"]["riskChannelsPassed"] == 0
    passed_return_cells = [
        cell
        for cell in payload["assetValidation"]["cells"]
        if cell["returnDirection"]["passed"]
    ]
    assert [
        (cell["assetGroup"], cell["horizonMonths"])
        for cell in passed_return_cells
    ] == [("商品", 3)]
    robustness = passed_return_cells[0]["returnDirection"][
        "regularizationRobustness"
    ]
    assert robustness["primaryBand"] == "central"
    assert robustness["stable"] is True
    assert all(band["passed"] for band in robustness["bands"].values())
    assert payload["current"]["date"] == "2026-06"
    assert len(payload["timeline"]) > 200
    assert {row["family"] for row in payload["familyCoverage"]} == {
        "国内政策流动性",
        "信用传导",
        "全球美元流动性",
    }
    assert payload["current"]["coverageStatus"] == "full_three_layer_core"
    assert payload["confirmation"]["role"] == "独立确认，不进入C5核心"
    assert len(payload["forecastPath"]) == 12
    path_levels = [row["scenarioLevel"] for row in payload["forecastPath"]]
    path_changes = [
        round(path_levels[index] - path_levels[index - 1], 5)
        for index in range(1, len(path_levels))
    ]
    assert len(set(path_changes)) > 3
    assert payload["timeline"][-1]["date"] == "2026-06"
