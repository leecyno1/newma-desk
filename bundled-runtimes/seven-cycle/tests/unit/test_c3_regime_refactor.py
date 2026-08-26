from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_c3_regime_refactor import (  # noqa: E402
    FORBIDDEN_INPUTS,
    OUTPUT_PATH,
    _country_features,
)


def test_c3_features_do_not_use_asset_prices() -> None:
    country = pd.DataFrame(
        {
            "year": range(1990, 2025),
            "gdp": [100 + index * 4 for index in range(35)],
            "cpi": [100 + index * 2 for index in range(35)],
            "rgdpmad": [100 + index * 3 for index in range(35)],
            "iy": [0.20 + (index % 7) * 0.002 for index in range(35)],
            "tbus": [40 + index * 2 for index in range(35)],
            "stir": [3.0 + (index % 5) * 0.2 for index in range(35)],
            "eq_tr": [0.5] * 35,
        }
    )

    features = _country_features(country)

    assert not set(FORBIDDEN_INPUTS) & set(features.columns)
    assert set(features.columns) == {
        "investment_impulse3",
        "business_credit_impulse3",
        "real_gdp_growth3",
        "financing_easing3",
        "investment_position",
    }


def test_c3_generated_output_keeps_asset_forecast_blocked() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload["meta"]["modelVersion"] == "c3-dual-core-v1"
    assert payload["state"]["current"]["phase"] in {
        "recovery",
        "expansion",
        "slowdown",
        "contraction",
    }
    assert payload["state"]["parameterRobustness"]["phaseAgreement"] == 1.0
    assert payload["architectureComparison"]["selectedArchitecture"] == "dual_core"
    assert payload["assetValidation"]["passedTargets"] < payload["assetValidation"]["targetCount"]
    assert payload["decision"]["assetForecastStatus"] == "blocked"
