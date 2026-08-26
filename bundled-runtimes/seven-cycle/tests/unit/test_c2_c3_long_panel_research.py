from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import scripts.research_c2_c3_long_panel as long_panel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research_c2_c3_long_panel import (
    OUTPUT_PATH,
    _align_bridge_factor,
    _fetch_oecd_short_rates,
    _model_frame,
    _target_direction_agreement,
    causal_robust_z,
)


def test_causal_robust_z_does_not_revise_past_when_future_is_appended() -> None:
    index = pd.Index(range(1900, 1980), name="year")
    series = pd.Series(np.sin(np.arange(len(index)) / 4.0) + np.arange(len(index)) * 0.01, index=index)

    full = causal_robust_z(series)
    truncated = causal_robust_z(series.loc[:1955])

    pd.testing.assert_series_equal(full.loc[:1955], truncated)


def test_model_frame_targets_the_requested_future_horizon() -> None:
    years = np.arange(1900, 1960)
    panel = pd.DataFrame(
        {
            "iso": ["AAA"] * len(years),
            "year": years,
            "factor": np.linspace(-1.0, 1.0, len(years)),
            "family_test": np.linspace(-0.5, 0.5, len(years)),
        }
    )

    frame, feature_columns = _model_frame(panel, horizon=3)
    row = frame.loc[frame["year"] == 1930].iloc[0]

    assert row["future_factor"] == panel.loc[panel["year"] == 1933, "factor"].iloc[0]
    assert row["target_up"] == 1.0
    assert "family_test" in feature_columns
    assert "lag_3" in feature_columns


def test_bridge_alignment_cutoff_does_not_use_future_scale_changes() -> None:
    years = np.arange(1980, 2021)
    historical = pd.DataFrame(
        {
            "iso": ["AAA"] * len(years),
            "year": years,
            "factor": np.linspace(-1.0, 1.0, len(years)),
        }
    )
    bridge = historical.copy()
    bridge["factor"] = bridge["factor"] * 2.0 + 0.5
    bridge.loc[bridge["year"] > 2005, "factor"] *= 20.0

    full = _align_bridge_factor(
        historical,
        bridge,
        alignment_end_year=2005,
    )
    truncated = _align_bridge_factor(
        historical,
        bridge.loc[bridge["year"] <= 2005],
        alignment_end_year=2005,
    )

    pd.testing.assert_series_equal(
        full.loc[full["year"] <= 2005, "factor"].reset_index(drop=True),
        truncated["factor"].reset_index(drop=True),
    )


def test_target_direction_agreement_detects_factor_definition_changes() -> None:
    years = np.arange(1900, 1980)
    baseline = pd.DataFrame(
        {
            "iso": ["AAA"] * len(years),
            "year": years,
            "factor": np.sin(np.arange(len(years)) / 4.0),
            "family_test": np.cos(np.arange(len(years)) / 5.0),
        }
    )
    matching = baseline.copy()
    inverted = baseline.copy()
    inverted["factor"] *= -1.0

    matching_result = _target_direction_agreement(baseline, matching, 1)
    inverted_result = _target_direction_agreement(baseline, inverted, 1)

    assert matching_result["agreement"] == 1.0
    assert inverted_result["agreement"] < 0.10


def test_oecd_short_rate_parser_preserves_series_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "short-rates.csv"
    pd.DataFrame(
        {
            "REF_AREA": ["USA", "GBR"],
            "FREQ": ["A", "A"],
            "MEASURE": ["IR3TIB", "IR3TIB"],
            "UNIT_MEASURE": ["PA", "PA"],
            "METHODOLOGY": ["N", "N"],
            "TIME_PERIOD": [2025, 2025],
            "OBS_VALUE": [4.25, 4.10],
        }
    ).to_csv(source, index=False)
    monkeypatch.setattr(long_panel, "_download", lambda *args, **kwargs: source)

    rates = _fetch_oecd_short_rates()

    assert rates.to_dict(orient="records") == [
        {"iso": "GBR", "year": 2025, "short_term_rate": 4.10},
        {"iso": "USA", "year": 2025, "short_term_rate": 4.25},
    ]


def test_generated_long_panel_research_preserves_governance() -> None:
    assert OUTPUT_PATH.exists()
    payload = json.loads(Path(OUTPUT_PATH).read_text(encoding="utf-8"))

    assert payload["meta"]["historicalEnd"] == 2020
    assert payload["meta"]["currentBridgeEnd"] >= 2025
    assert set(payload["cycles"]) == {"C2", "C3"}
    for cycle in payload["cycles"].values():
        assert cycle["status"] == "directionally_predictable"
        assert cycle["governance"]["formalStatus"] == "blocked"
        assert cycle["validation"]["1y"]["accuracy"] > cycle["validation"]["1y"]["momentumAccuracy"]
        assert cycle["validation"]["3y"]["accuracy"] > cycle["validation"]["3y"]["momentumAccuracy"]
        assert cycle["validation"]["1y"]["leaveCountryOut2000Plus"]["accuracy"] > 0.65
        assert cycle["validation"]["3y"]["leaveCountryOut2000Plus"]["accuracy"] > 0.65
        assert cycle["familyAblation"]["groupCount"] >= 4
        assert cycle["familyAblation"]["passedGroups"] <= cycle[
            "familyAblation"
        ]["groupCount"]
        assert cycle["familyAblation"]["maximumAbsoluteCurrentProbabilityShift"] >= 0
        assert cycle["independentOutcomeValidation"]["status"] == "failed"
        assert cycle["independentOutcomeValidation"]["cellCount"] == 6
        assert cycle["independentOutcomeValidation"]["passedCells"] < cycle[
            "independentOutcomeValidation"
        ]["requiredPassedCells"]
        assert len(cycle["independentOutcomeValidation"]["coveredOutcomes"]) < 3
        for cell in cycle["independentOutcomeValidation"]["cells"]:
            assert cell["observations"] >= 800
            assert len(cell["subperiods"]) == 2
            assert 0 <= cell["auc"] <= 1
            assert 0 <= cell["baselineAuc"] <= 1
            assert -1 <= cell["aucImprovement"] <= 1
            assert -1 <= cell["brierImprovement"] <= 1
            if cell["passed"]:
                assert cell["aucImprovement"] >= cycle[
                    "independentOutcomeValidation"
                ]["gates"]["minimumAucImprovement"]
                assert cell["brierImprovement"] >= cycle[
                    "independentOutcomeValidation"
                ]["gates"]["minimumBrierImprovement"]
        for ablation in cycle["familyAblation"]["groups"]:
            assert set(ablation["horizons"]) == {"1y", "3y"}
            assert all(
                horizon["targetAgreement"]["agreement"] >= 0
                for horizon in ablation["horizons"].values()
            )
        assert len(cycle["bridgeHistory"]) > 20
        assert {row["horizonYears"] for row in cycle["currentForecasts"]} == {1, 2, 3}

    c2 = payload["cycles"]["C2"]
    assert c2["independentOutcomeValidation"]["passedCells"] == 0
    assert c2["partialNowcast"]["status"] == "limited_partial_year"
    assert c2["partialNowcast"]["asOfPeriod"] == "2026-Q1"
    assert c2["partialNowcast"]["validation"]["status"] == "passed_limited"
    assert "只用当时已经存在的重叠历史" in c2["partialNowcast"]["validation"]["method"]
    assert c2["partialNowcast"]["validation"]["directionAccuracy"] >= 0.60
    assert c2["currentForecasts"][0]["asOfPeriod"] == "2026-Q1"
    assert c2["currentForecasts"][0]["latestYearCountryCount"] >= 6
    assert c2["factorArchitecture"]["definition"] == "地产—信用核心与宏观传播分层系统"
    assert c2["factorArchitecture"]["coreFamilies"] == [
        "housing_momentum",
        "mortgage_credit",
    ]
    assert c2["factorArchitecture"]["confirmationFamilies"] == [
        "investment_confirmation",
        "financing_conditions",
    ]
    assert c2["factorArchitecture"]["defaultDirectionModelFamilies"] == [
        "housing_momentum",
        "mortgage_credit",
    ]
    assert len(c2["factorArchitecture"]["propagationFamilies"]) == 5
    architecture = c2["architectureComparison"]
    assert architecture["selectedArchitecture"] == "core_composite"
    architecture_by_id = {
        row["architectureId"]: row for row in architecture["architectures"]
    }
    core_score = architecture_by_id["core_composite"]["summary"]["score"]
    assert core_score > architecture_by_id["housing_single"]["summary"]["score"]
    assert core_score > architecture_by_id["mortgage_single"]["summary"]["score"]
    assert core_score > architecture_by_id["broad_equal_composite"]["summary"]["score"]
    assert core_score > architecture_by_id["macro_propagation"]["summary"]["score"]
    assert architecture["recommendation"]["propagationBrierGain"] > 0
    assert architecture["recommendation"]["propagationAccuracyGain"] < 0
    assert architecture["recommendation"]["propagationCountryHoldoutAccuracyGain"] < 0
    assert architecture["recommendation"]["externalOutcomePassedCells"] == 0
    house_source = next(
        source
        for source in payload["sources"]
        if source["name"] == "OECD Analytical House Price Indicators"
    )
    assert "房价租金比" in house_source["coverage"]
    assert house_source["cache"].endswith("OECD_HOUSE_PRICE_TO_RENT.csv")
    world_bank_source = next(
        source for source in payload["sources"] if source["name"] == "World Bank WDI"
    )
    assert "贷款利率" in world_bank_source["coverage"]
    assert any(
        cache["cache"].endswith("world_bank_FR_INR_LEND.json")
        for cache in world_bank_source["caches"]
    )

    c3 = payload["cycles"]["C3"]
    assert c3["independentOutcomeValidation"]["passedCells"] == 2
    assert c3["independentOutcomeValidation"]["coveredOutcomes"] == [
        "consumption_acceleration",
        "unemployment_improvement",
    ]
    assert c3["partialNowcast"]["status"] == "limited_partial_year"
    assert c3["partialNowcast"]["asOfPeriod"] == "2026-Q1"
    assert c3["partialNowcast"]["validation"]["status"] == "passed_limited"
    assert "只用当时已经存在的重叠历史" in c3["partialNowcast"]["validation"]["method"]
    assert c3["partialNowcast"]["validation"]["observations"] >= 12
    assert c3["partialNowcast"]["validation"]["directionAccuracy"] >= 0.60
    assert c3["currentForecasts"][0]["asOfPeriod"] == "2026-Q1"
