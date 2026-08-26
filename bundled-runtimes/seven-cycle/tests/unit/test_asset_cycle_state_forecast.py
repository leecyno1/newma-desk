from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_asset_cycle_state_forecast import (
    ANALOG_PRIOR_OBSERVATIONS,
    ASYNCHRONOUS_CLOCK,
    OUTPUT_PATH,
    SYNCHRONOUS_CLOCK,
    STRONG_ANALOG_PRIOR_OBSERVATIONS,
    STRONG_SHRINK_MIN_BRIER_IMPROVEMENT,
    STRONG_SHRINK_MIN_OOS_R2,
    STRONG_SHRINK_MIN_RELATIVE_MAE_IMPROVEMENT,
    build_asset_feature_frame,
    build_feature_frame,
    _freshness_status,
    _nested_champion_validation,
    _recency_analog_estimate,
    _shrunk_analog_estimate,
    _validation_with_recent,
    _validation_uncertainty,
)


def test_release_clock_uses_lagged_c4_c5_and_current_c7() -> None:
    asynchronous = build_feature_frame(ASYNCHRONOUS_CLOCK)
    synchronous = build_feature_frame(SYNCHRONOUS_CLOCK)

    assert asynchronous.index[-1].strftime("%Y-%m") == "2026-07"
    assert synchronous.index[-1].strftime("%Y-%m") == "2026-06"
    assert asynchronous.iloc[-1]["c4_level"] == synchronous.iloc[-1]["c4_level"]
    assert asynchronous.iloc[-1]["c5_state"] == synchronous.iloc[-1]["c5_state"]
    assert asynchronous.iloc[-1]["c7_state"] != synchronous.iloc[-1]["c7_state"]


def test_asset_cycle_state_forecast_preserves_asset_gates() -> None:
    assert OUTPUT_PATH.exists()
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload["meta"]["asOf"] == "2026-07"
    assert payload["meta"]["assetDataThrough"] == "2026-07"
    assert payload["meta"]["forecastClock"] == ASYNCHRONOUS_CLOCK
    assert payload["meta"]["modelVersion"] == "asset_cycle_state_v8_cycle_shapley"
    assert payload["meta"]["modelPolicies"] == {
        "1": "nested_champion",
        "3": "nested_model_average",
        "6": "fixed_state_analog_shrunk",
    }
    assert payload["clockComparison"]["status"] == "paired_recent_nested_oos"
    assert payload["clockComparison"]["referenceClock"] == SYNCHRONOUS_CLOCK
    assert payload["meta"]["notPortfolioBacktest"] is True
    assert payload["meta"]["attributionStability"]["assets"] == 10
    assert sum(
        payload["meta"]["attributionStability"]["statusCounts"].values()
    ) == 10
    assert payload["summary"]["assets"] == 98
    assert payload["summary"]["refreshedAssets"] == 81
    assert payload["summary"]["sourceLagAssets"] == 17
    assert payload["summary"]["staleAssets"] == 0
    assert {asset["majorCategory"] for asset in payload["assets"]} == {
        "股票",
        "债券",
        "商品",
        "外汇",
    }
    assert all(
        asset["majorCategory"] == "债券"
        for asset in payload["assets"]
        if asset["category"] == "各类债券指数"
    )
    for horizon in ("1", "6"):
        assert payload["summary"]["horizons"][horizon]["validatedAssets"] == 93
        assert payload["summary"]["horizons"][horizon]["researchForecastAssets"] == 97
    assert payload["summary"]["horizons"]["3"]["validatedAssets"] == 72
    assert payload["summary"]["horizons"]["3"]["researchForecastAssets"] == 97
    for horizon in ("1", "3", "6"):
        summary = payload["summary"]["horizons"][horizon]
        assert summary["nestedValidatedAssets"] >= 60
        assert 0 <= summary["nestedQualifiedAssets"] <= summary["nestedValidatedAssets"]
        assert (
            0 < summary["nestedRecentStableAssets"] <= summary["nestedValidatedAssets"]
        )
        assert 0 <= summary["qualifiedAssets"] <= summary["fullSampleQualifiedAssets"]
    assert sum(
        payload["summary"]["horizons"][horizon]["nestedQualifiedAssets"]
        for horizon in ("1", "3", "6")
    ) > 0
    assert sum(
        payload["summary"]["horizons"][horizon]["qualifiedAssets"]
        for horizon in ("1", "3", "6")
    ) > 0
    qualified_three_month_assets = {
        asset["name"]
        for asset in payload["assets"]
        if asset["horizons"]["3"]["publicationQualified"]
    }
    assert qualified_three_month_assets == {"原油", "石油石化"}
    qualified_six_month_assets = {
        asset["name"]
        for asset in payload["assets"]
        if asset["horizons"]["6"]["publicationQualified"]
    }
    assert qualified_six_month_assets == {
        "德国ETF(EWG)",
        "标普500(SPY)",
        "纳指100(QQQ)",
        "美股信息科技(XLK)",
        "美股原材料(XLB)",
        "美股能源(XLE)",
        "美股金融(XLF)",
    }
    assert (
        "non_overlapping_instability"
        not in payload["summary"]["horizons"]["1"]["blockedReasonCounts"]
    )
    assert (
        payload["summary"]["horizons"]["3"]["blockedReasonCounts"][
            "non_overlapping_instability"
        ]
        >= 50
    )
    assert (
        payload["summary"]["horizons"]["6"]["blockedReasonCounts"][
            "non_overlapping_instability"
        ]
        >= 50
    )
    assert payload["governance"]["publicationStatus"] == "limited"
    assert {asset["status"] for asset in payload["assets"]} == {"limited", "blocked"}
    ff17_assets = [
        asset for asset in payload["assets"] if asset["category"] == "FF 17行业组合(US)"
    ]
    assert len(ff17_assets) == 17
    assert all(asset["observations"] >= 240 for asset in ff17_assets)
    assert all(asset["freshnessStatus"] == "source_lag" for asset in ff17_assets)
    assert all(asset["lagMonths"] == 1 for asset in ff17_assets)
    assert payload["governance"]["sourceReportingLagLimits"] == {
        "FF 17行业组合(US)": 2
    }
    for horizon in ("1", "3", "6"):
        qualified = [
            asset["horizons"][horizon]
            for asset in payload["assets"]
            if asset["horizons"][horizon]["publicationQualified"]
        ]
        assert (
            len(qualified) == payload["summary"]["horizons"][horizon]["qualifiedAssets"]
        )
        assert all(result["publicationReasonCodes"] == [] for result in qualified)
        assert all(result["validation"]["qualified"] for result in qualified)
        assert all(result["validation"]["recentStable"] for result in qualified)
        for result in qualified:
            attribution = result["cycleAttribution"]
            assert attribution["method"] == "shapley_current_state_neutralization"
            assert attribution["cycles"] == ["C4", "C5", "C7"]
            assert attribution["notCausal"] is True
            for metric in (
                "probabilityUp",
                "medianReturn",
                "conditionalVol",
                "valueAtRisk95",
            ):
                reconstructed = attribution["baseline"][metric] + sum(
                    attribution["contributions"][cycle_id][metric]
                    for cycle_id in attribution["cycles"]
                )
                assert np.isclose(
                    reconstructed,
                    attribution["full"][metric],
                    atol=2e-6,
                )
                assert np.isclose(
                    attribution["full"][metric],
                    result["forecast"][metric],
                    atol=1e-6,
                )
            stability = result["cycleAttributionStability"]
            assert stability["status"] in {
                "stable",
                "mixed",
                "unstable",
                "low_impact",
            }
            assert stability["observations"] == 24
            assert stability["spacingMonths"] == int(horizon)
            assert stability["currentDominantCycle"] in {"C4", "C5", "C7"}
            assert 0 <= stability["dominantPersistence"] <= 1
            assert stability["materiality"] in {"high", "medium", "low"}
            assert stability["notForecastAccuracy"] is True
    for asset in ff17_assets:
        for result in asset["horizons"].values():
            assert result["publicationQualified"] is False
            assert "source_reporting_lag" in result["publicationReasonCodes"]


def test_asset_cycle_state_forecast_exposes_champion_and_risk_fields() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    models = {
        "state_analog",
        "state_analog_shrunk",
        "state_analog_strong_shrink",
        "state_analog_recency",
        "state_ridge",
        "category_context_ridge",
        "state_model_consensus",
        "nested_model_average",
    }

    for asset in payload["assets"]:
        for horizon, result in asset["horizons"].items():
            selection = result["selectionValidation"]
            expected_selection_model = {
                "1": "nested_walk_forward",
                "3": "nested_model_average",
                "6": "state_analog_shrunk",
            }
            assert selection["model"] == expected_selection_model[horizon]
            assert "_fullTrace" not in selection
            assert "_selectionHistory" not in selection
            if horizon == "6":
                assert result["selectionPolicy"] == "fixed_model"
                assert result["championModel"] == "state_analog_shrunk"
            else:
                assert selection["switches"] >= 0
            if selection["observations"] >= 36:
                uncertainty = selection["uncertainty"]
                assert uncertainty["evidenceStrength"] in {
                    "strong",
                    "moderate",
                    "weak",
                }
                assert (
                    uncertainty["directionAccuracy"]["low"]
                    <= uncertainty["directionAccuracy"]["high"]
                )
            assert result["championModel"] in models
            if horizon == "3":
                assert result["championModel"] == "nested_model_average"
                assert selection["topModelCount"] == 4
                assert set(selection["ensembleSizeRobustness"]["sizes"]) == {
                    "3",
                    "4",
                    "5",
                }
            if result["publicationQualified"] and horizon == "6":
                assert result["synchronousReferenceStable"] is True
            assert (
                {
                    "state_analog",
                    "state_analog_shrunk",
                    "state_analog_recency",
                    "state_ridge",
                }
                <= set(result["models"])
                <= models
            )
            assert result["validation"]["reasonCodes"] is not None
            assert result["validation"]["recentValidation"] is not None
            assert result["validation"]["recentStable"] in {True, False}
            assert "_fullTrace" not in result["validation"]
            assert result["publicationReasonCodes"] is not None
            forecast = result["forecast"]
            if forecast is None:
                continue
            assert forecast["model"] == result["championModel"]
            assert 0 <= forecast["downsideProbability"] <= 1
            assert forecast["expectedShortfall95"] <= forecast["valueAtRisk95"]
            if forecast["model"] == "state_model_consensus":
                assert forecast["componentCount"] in {2, 3}
            if forecast["model"] == "nested_model_average":
                assert forecast["componentCount"] == 4
                assert len(forecast["componentModels"]) == 4
                assert set(forecast["ensembleSizeSensitivity"]) == {"3", "4", "5"}
            if forecast["model"] == "state_analog_strong_shrink":
                assert forecast["localWeight"] == 0.142857


def test_asset_cycle_state_forecast_exposes_recent_oos_trace() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    for asset in payload["assets"]:
        for result in asset["horizons"].values():
            trace = result["validation"]["recentTrace"]
            if result["validation"]["observations"] == 0:
                assert trace == []
                continue
            assert 0 < len(trace) <= 48
            assert list(trace[0]) == [
                "date",
                "actualReturn",
                "predictedReturn",
                "baselineReturn",
                "probabilityUp",
            ]
            assert all(0 <= point["probabilityUp"] <= 1 for point in trace)
            assert all(
                "recentTrace" not in model_result["validation"]
                for model_result in result["models"].values()
            )


def test_stale_assets_are_not_published_as_current_forecasts() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    stale_assets = [
        asset for asset in payload["assets"] if not asset["currentDataAvailable"]
    ]

    assert stale_assets
    for asset in stale_assets:
        assert asset["qualifiedHorizons"] == []
        assert asset["status"] == "blocked"
        for result in asset["horizons"].values():
            assert result["publicationQualified"] is False
            assert {
                "source_reporting_lag",
                "stale_asset_data",
            } & set(result["publicationReasonCodes"])


def test_asset_data_ahead_of_cycle_cutoff_remains_current() -> None:
    status, lag_months = _freshness_status(
        pd.Timestamp("2026-06-30"),
        pd.Timestamp("2026-07-31"),
    )

    assert status == "current"
    assert lag_months == -1


def test_source_reporting_lag_is_category_specific() -> None:
    current_date = pd.Timestamp("2026-07-31")
    asset_end = pd.Timestamp("2026-05-31")

    ff17_status, ff17_lag = _freshness_status(
        current_date,
        asset_end,
        category="FF 17行业组合(US)",
    )
    other_status, other_lag = _freshness_status(
        current_date,
        asset_end,
        category="海外指数/ETF",
    )

    assert (ff17_status, ff17_lag) == ("source_lag", 2)
    assert (other_status, other_lag) == ("stale", 2)


def test_recency_analog_gives_more_weight_to_recent_neighbors() -> None:
    index = pd.date_range("2010-01-31", periods=24, freq="12ME")
    analogs = pd.Series([-0.10] * 12 + [0.10] * 12, index=index)

    estimate = _recency_analog_estimate(
        analogs,
        pd.Timestamp("2034-01-31"),
        60.0,
    )

    assert estimate["probabilityUp"] > 0.5
    assert estimate["medianReturn"] == 0.10


def test_non_overlapping_validation_uses_independent_month_paths() -> None:
    dates = (
        pd.date_range("2010-01-31", periods=90, freq="ME").strftime("%Y-%m").tolist()
    )
    actual = [0.03 if index % 2 == 0 else -0.02 for index in range(90)]
    probabilities = [0.8 if value > 0 else 0.2 for value in actual]

    validation = _validation_with_recent(
        model="state_analog",
        horizon=3,
        dates=dates,
        actual=actual,
        predicted=actual,
        probabilities=probabilities,
        baseline=[0.0] * 90,
        baseline_probabilities=[0.5] * 90,
    )

    independent = validation["nonOverlappingValidation"]
    assert independent["eligiblePaths"] == 3
    assert independent["stablePaths"] == 3
    assert independent["stable"] is True
    assert {path["observations"] for path in independent["paths"]} == {30}


def test_nested_champion_selection_does_not_use_future_results() -> None:
    dates = (
        pd.date_range("2010-01-31", periods=150, freq="ME").strftime("%Y-%m").tolist()
    )
    actual = [0.03 if index % 2 == 0 else -0.02 for index in range(150)]

    def candidate_trace(model: str, first_regime: bool) -> dict[str, object]:
        trace = []
        for index, (date, actual_return) in enumerate(zip(dates, actual)):
            model_is_correct = index < 65 if first_regime else index >= 65
            predicted_return = actual_return if model_is_correct else -actual_return
            trace.append(
                {
                    "date": date,
                    "actualReturn": actual_return,
                    "predictedReturn": predicted_return,
                    "baselineReturn": 0.0,
                    "probabilityUp": 0.8 if predicted_return > 0 else 0.2,
                    "baselineProbabilityUp": 0.5,
                }
            )
        return {"model": model, "_fullTrace": trace}

    validation = _nested_champion_validation(
        {
            "state_analog": candidate_trace("state_analog", True),
            "state_ridge": candidate_trace("state_ridge", False),
        },
        horizon=1,
    )

    selections = validation["_selectionHistory"]
    switch_date = dates[65]
    selected_at_switch = next(
        point["model"] for point in selections if point["date"] == switch_date
    )
    assert selected_at_switch == "state_analog"
    assert selections[-1]["model"] == "state_ridge"


def test_validation_uncertainty_reports_strong_perfect_signal() -> None:
    trace = [
        {
            "actualReturn": 0.03 if index % 2 == 0 else -0.02,
            "predictedReturn": 0.03 if index % 2 == 0 else -0.02,
            "baselineReturn": 0.0,
        }
        for index in range(90)
    ]

    uncertainty = _validation_uncertainty(trace, horizon=3)

    assert uncertainty is not None
    assert uncertainty["directionAccuracy"]["low"] > 0.9
    assert uncertainty["oosR2"]["low"] > 0.9
    assert uncertainty["evidenceStrength"] == "strong"


def test_asset_cycle_state_forecast_never_produces_portfolio_fields() -> None:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    forbidden = {"portfolio", "weight", "weights", "allocation"}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden.isdisjoint({str(key).lower() for key in value})
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)


def test_asset_feature_frame_is_cutoff_invariant() -> None:
    index = pd.date_range("2010-01-31", periods=48, freq="ME")
    state = pd.DataFrame(
        {
            "c4_level": np.linspace(-1, 1, len(index)),
            "c4_slope3": np.linspace(0.2, -0.2, len(index)),
            "c5_state": np.sin(np.arange(len(index)) / 3),
            "c5_slope3": np.cos(np.arange(len(index)) / 4),
            "c7_state": np.sin(np.arange(len(index)) / 2),
            "c7_slope3": np.cos(np.arange(len(index)) / 2),
        },
        index=index,
    )
    returns = pd.Series(np.linspace(-0.03, 0.04, len(index)), index=index)
    original = build_asset_feature_frame(state, returns)
    revised_returns = returns.copy()
    revised_returns.loc[index[36] :] = 0.5
    revised = build_asset_feature_frame(state, revised_returns)

    pd.testing.assert_frame_equal(
        original.loc[: index[35]],
        revised.loc[: index[35]],
    )


def test_category_context_features_are_cutoff_invariant() -> None:
    index = pd.date_range("2010-01-31", periods=48, freq="ME")
    state = pd.DataFrame(
        {
            "c4_level": np.linspace(-1, 1, len(index)),
            "c4_slope3": np.linspace(0.2, -0.2, len(index)),
            "c5_state": np.sin(np.arange(len(index)) / 3),
            "c5_slope3": np.cos(np.arange(len(index)) / 4),
            "c7_state": np.sin(np.arange(len(index)) / 2),
            "c7_slope3": np.cos(np.arange(len(index)) / 2),
        },
        index=index,
    )
    returns = pd.Series(np.linspace(-0.03, 0.04, len(index)), index=index)
    category = pd.Series(np.linspace(-0.02, 0.03, len(index)), index=index)
    original = build_asset_feature_frame(
        state,
        returns,
        category_returns=category,
    )
    revised_returns = returns.copy()
    revised_category = category.copy()
    revised_returns.loc[index[36] :] = 0.5
    revised_category.loc[index[36] :] = -0.5
    revised = build_asset_feature_frame(
        state,
        revised_returns,
        category_returns=revised_category,
    )

    pd.testing.assert_frame_equal(
        original.loc[: index[35]],
        revised.loc[: index[35]],
    )


def test_shrunk_analog_uses_fixed_history_prior() -> None:
    analogs = pd.Series([0.10] * 18 + [-0.10] * 6)
    training = pd.Series([0.02] * 36 + [-0.02] * 36)

    estimate = _shrunk_analog_estimate(analogs, training)

    expected_weight = len(analogs) / (len(analogs) + ANALOG_PRIOR_OBSERVATIONS)
    assert estimate["localWeight"] == expected_weight
    assert estimate["return"] == expected_weight * analogs.median()
    assert (
        estimate["probabilityUp"]
        == expected_weight * 0.75 + (1 - expected_weight) * 0.5
    )


def test_strong_shrink_analog_uses_double_history_prior() -> None:
    analogs = pd.Series([0.10] * 18 + [-0.10] * 6)
    training = pd.Series([0.02] * 36 + [-0.02] * 36)

    estimate = _shrunk_analog_estimate(
        analogs,
        training,
        prior_observations=STRONG_ANALOG_PRIOR_OBSERVATIONS,
    )

    expected_weight = len(analogs) / (len(analogs) + STRONG_ANALOG_PRIOR_OBSERVATIONS)
    assert estimate["localWeight"] == expected_weight
    assert expected_weight < len(analogs) / (len(analogs) + ANALOG_PRIOR_OBSERVATIONS)
    assert STRONG_SHRINK_MIN_OOS_R2 > 0
    assert STRONG_SHRINK_MIN_RELATIVE_MAE_IMPROVEMENT > 0
    assert STRONG_SHRINK_MIN_BRIER_IMPROVEMENT > 0
