from __future__ import annotations

import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.build_web_research_data import (
    CYCLE_IDENTIFICATION_TRACK_IDS,
    build,
)


def test_web_research_products_preserve_governance_and_real_data(tmp_path: Path, monkeypatch) -> None:
    import scripts.build_web_research_data as builder

    monkeypatch.setattr(builder, "WEB_DATA_DIR", tmp_path)
    outputs = build(refresh_public=False, as_of="2026-07-20")

    market = json.loads(outputs["market"].read_text(encoding="utf-8"))
    assert market["meta"]["defaultTrackIds"] == CYCLE_IDENTIFICATION_TRACK_IDS
    presets = {preset["id"]: preset for preset in market["meta"]["trackPresets"]}
    assert presets["cycle"]["trackIds"] == CYCLE_IDENTIFICATION_TRACK_IDS
    assert len(presets) == 1
    assert market["meta"]["trackCount"] == 104
    assert market["meta"]["groupCounts"]["market"] >= 70
    assert market["meta"]["groupCounts"]["economic"] >= 30
    assert market["meta"]["governedCycles"] == ["C4", "C6"]
    assert market["meta"]["researchOnlyCycles"] == ["C2", "C3", "C5", "C7"]
    assert "2025-12" <= market["meta"]["asOf"] <= "2026-07"
    assert market["meta"]["forecastVintage"] in {"2025-12", "2026-06"}
    forecast_year, forecast_month = map(int, market["meta"]["forecastVintage"].split("-"))
    assert market["meta"]["forecastStaleMonths"] == (2026 * 12 + 7) - (forecast_year * 12 + forecast_month)

    tracks = {track["id"]: track for track in market["tracks"]}
    audit = json.loads(outputs["audit"].read_text(encoding="utf-8"))
    pmi_source = next(
        source for source in audit["sources"] if source["entity"] == "美国 PMI（新订单代理）"
    )
    assert pmi_source["source"] == "FRED: AMTMNO 制造商新订单"
    assert pmi_source["status"] == "explicit_leading_proxy_not_pmi_level"
    assert set(CYCLE_IDENTIFICATION_TRACK_IDS) <= set(tracks)
    assert tracks["us_industrial_production"]["sourceCode"] == "INDPRO"
    assert tracks["us_industrial_production"]["coverage"]["start"] < "1921-01"
    assert tracks["us_term_spread"]["sourceCode"] == "T10Y2Y"
    assert tracks["us_nfci"]["sourceCode"] == "NFCI"
    assert tracks["global_commodity"]["sourceCode"] == "PALLFNFINDEXM"
    assert tracks["global_commodity"]["source"] == "FRED / IMF"
    assert tracks["comex_gold"]["proxyStatus"] == "direct"
    assert tracks["comex_gold"]["source"] == "Yahoo Finance"
    assert tracks["us_pmi"]["proxyStatus"] == "proxy"
    pmi_proxy = next(
        track
        for track in market["tracks"]
        if track["sourceCode"] == "CN_PMI_PMI010402_LEVEL"
    )
    assert pmi_proxy["proxyStatus"] == "proxy"
    assert "显式OLS尾部代理" in pmi_proxy["source"]
    assert market["meta"]["staleTrackCounts"]["over12Months"] == 0
    assert tracks["sp500"]["coverage"]["changeObservations"] > 400
    assert tracks["sp500"]["coverage"]["observations"] > 100
    assert len(tracks["wti"]["dates"]) == len(tracks["wti"]["governedStack"])
    assert market["meta"]["forecastTrackCounts"]["limited"] >= 25
    assert tracks["wti"]["forecast"]["status"] == "limited"
    assert "多期限 Ridge" in tracks["wti"]["forecast"]["method"]
    assert tracks["wti"]["forecast"]["bridge"]["date"] == tracks["wti"]["coverage"]["end"]
    assert abs(
        tracks["wti"]["forecast"]["median"][0]
        - tracks["wti"]["forecast"]["bridge"]["value"]
    ) < 0.75
    assert len({round(value, 3) for value in tracks["wti"]["forecast"]["median"]}) > 12
    contribution = tracks["wti"]["cycleContribution"]
    assert contribution["status"] == "retrospective_diagnostic"
    assert abs(contribution["current"]["conservationError"]) < 1e-10
    assert len(contribution["paths"]["residual"]) == len(tracks["wti"]["dates"])
    assert set(contribution["current"]["components"]) <= {"C2", "C3", "C4", "C5", "C6", "C7"}
    assert contribution["filterRobustness"]["comparisonFilter"] == "butterworth_zero_phase"
    assert all(
        "filterRobustness" in component
        for component in contribution["current"]["components"].values()
    )
    realtime_confirmation = contribution["realtimeConfirmation"]
    assert realtime_confirmation["status"] == "causal_realtime_confirmation"
    assert abs(realtime_confirmation["current"]["conservationError"]) < 1e-10
    assert realtime_confirmation["training"]["originCount"] >= 8
    assert math.isfinite(
        realtime_confirmation["training"]["rollingReconstructionR2"]
    )
    assert math.isfinite(
        realtime_confirmation["training"][
            "equalMedianRollingReconstructionR2"
        ]
    )
    assert realtime_confirmation["training"]["peerSharedStatus"] in {
        "adopted",
        "rejected",
    }
    assert realtime_confirmation["training"]["causalOrthogonalStatus"] in {
        "adopted",
        "rejected",
    }
    assert realtime_confirmation["training"]["peerSharedEligibleCycles"]
    assert all(
        component["status"] in {"limited_confirmed", "weak"}
        and "coefficientSignAgreement" in component
        and "coefficientUncertaintyShare" in component
        and component["stateSpecificationCount"] == 3
        and "stateSpecificationDirectionAgreement" in component
        and abs(sum(component["stateSpecificationWeights"].values()) - 1.0)
        < 2e-6
        and component["peerSharedEligible"] is True
        and component["peerSharedPeerCount"] >= 3
        and 0.0 < component["peerSharedEvidenceWeight"] <= 0.5
        and component["stateWeightModel"] in {
            "track_only",
            "peer_shared",
            "dynamic_factor",
            "nearest_factor",
            "causal_orthogonal",
        }
        and "orthogonalSpanRollingDirectionAgreement" in component
        and component["uncertainty"] >= component["stateUncertainty"]
        for component in realtime_confirmation["current"]["components"].values()
    )
    contribution_study = market["indicatorContributionStudy"]
    assert contribution_study["notCausalAttribution"] is True
    assert contribution_study["cycles"]["C1"]["status"] == "excluded"
    assert contribution_study["cycles"]["C4"]["eligibleTracks"] > 50
    assert contribution_study["cycles"]["C4"]["directionAgreementTracks"] > 0
    assert contribution_study["cycles"]["C4"]["medianFilterPathCorrelation"] > 0
    assert contribution_study["cycles"]["C4"]["realtimeEligibleTracks"] > 50
    assert contribution_study["cycles"]["C4"]["realtimeConfirmedTracks"] > 10
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeDynamicFactorEligibleTracks"
        ]
        == contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeDynamicFactorAdoptedTracks"
        ]
        < contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeNearestFactorEligibleTracks"
        ]
        == contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
        - contribution_study["cycles"]["C4"][
            "realtimeLowTargetVarianceWarningTracks"
        ]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeNearestFactorAdoptedTracks"
        ]
        < contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeNearestFactorSpecificationStableTracks"
        ]
        <= contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeNearestFactorRobustlyAdoptedTracks"
        ]
        <= contribution_study["cycles"]["C4"][
            "realtimeNearestFactorAdoptedTracks"
        ]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeLowTargetVarianceWarningTracks"
        ]
        >= 0
    )
    assert math.isfinite(
        contribution_study["cycles"]["C4"][
            "medianRealtimeNearestFactorEarlyVintageR2Improvement"
        ]
    )
    assert math.isfinite(
        contribution_study["cycles"]["C4"][
            "medianRealtimeNearestFactorLateVintageR2Improvement"
        ]
    )
    assert (
        contribution_study["cycles"]["C4"]["realtimePeerSharedEligibleTracks"]
        == contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"]["realtimePeerSharedAdoptedTracks"]
        < contribution_study["cycles"]["C4"]["realtimeEligibleTracks"]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "realtimeCausalOrthogonalAdoptedTracks"
        ]
        > 0
    )
    assert (
        contribution_study["cycles"]["C4"][
            "medianRealtimeOrthogonalMaximumCorrelation"
        ]
        < contribution_study["cycles"]["C4"][
            "medianRealtimeBaseMaximumCorrelation"
        ]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "medianRealtimeOrthogonalConditionNumber"
        ]
        < contribution_study["cycles"]["C4"][
            "medianRealtimeBaseConditionNumber"
        ]
    )
    assert (
        contribution_study["cycles"]["C4"][
            "medianRealtimeCoefficientSignAgreement"
        ]
        >= 0.60
    )
    assert contribution_study["longHistory"]["frequency"] == "A"
    assert contribution_study["longHistory"]["cycles"]["C1"]["eligibleTracks"] > 0

    cycles = json.loads(outputs["cycles"].read_text(encoding="utf-8"))
    policies = {
        row["id"]: row["publication"] for row in cycles["governance"]["cycles"]
    }
    assert policies["C1"]["historical"] == "scenario_only"
    assert policies["C4"]["historical"] == "formal"
    assert policies["C6"]["forecast"] == "calendar_only"
    assert {
        policies[cycle_id]["historical"]
        for cycle_id in ("C2", "C3", "C5", "C7")
    } == {"blocked"}
    assert cycles["C1"]["status"] == "scenario_only"
    assert len(cycles["C1"]["dates"]) > 400
    assert cycles["C4"]["status"] == "identifiable"
    assert set(cycles["diagnostics"]) == {"C2", "C3", "C5", "C7"}
    assert cycles["indicatorContributionStudy"] == contribution_study
    for cycle_id, diagnostic in cycles["diagnostics"].items():
        assert diagnostic["publicationStatus"] == "blocked"
        assert diagnostic["status"] == "research_diagnostic"
        assert len(diagnostic["dates"]) > 100
        assert len(diagnostic["candidateBands"]) == 3
        assert diagnostic["current"]["direction"] in {
            "上行增强",
            "高位放缓",
            "低位修复",
            "下行增强",
        }
        assert diagnostic["modelRebuild"]["recommended"]
        assert len(diagnostic["unlockConditions"]) >= 3
    for cycle_id in ("C2", "C3"):
        long_panel = cycles["diagnostics"][cycle_id]["longPanel"]
        assert long_panel["status"] == "directionally_predictable"
        assert long_panel["governance"]["formalStatus"] == "blocked"
        assert long_panel["validation"]["1y"]["accuracy"] > 0.65
        assert long_panel["validation"]["3y"]["accuracy"] > 0.65
        assert long_panel["familyAblation"]["groupCount"] >= 4
        assert long_panel["familyAblation"]["status"] in {
            "passed_limited",
            "failed",
        }
        assert long_panel["independentOutcomeValidation"]["status"] == "failed"
        assert long_panel["independentOutcomeValidation"]["passedCells"] < long_panel[
            "independentOutcomeValidation"
        ]["requiredPassedCells"]
        assert all(
            "aucImprovement" in cell and "brierImprovement" in cell
            for cell in long_panel["independentOutcomeValidation"]["cells"]
        )
        assert cycles["diagnostics"][cycle_id]["directionPublication"][
            "independentOutcomeStatus"
        ] == "failed"
        assert cycles["diagnostics"][cycle_id]["directionPublication"][
            "badgeLabel"
        ] == "因子方向可用"
        assert long_panel["partialNowcast"]["validation"]["status"] == "passed_limited"
        assert long_panel["currentForecasts"][0]["asOfPeriod"] == "2026-Q1"
        if cycle_id == "C2":
            regime = cycles["diagnostics"][cycle_id]["regimeRefactor"]
            assert regime["meta"]["modelVersion"] == (
                "c2-conditional-propagation-v12"
            )
            assert regime["state"]["current"]["phase"] == "contraction"
            assert regime["state"]["transitionEvidence"]["status"] == "not_confirmed"
            assert regime["state"]["familyStates"]["coreFamilyCount"] == 2
            assert regime["historicalDating"]["lookAhead"] is True
            assert len(regime["historicalDating"]["turningPoints"]) >= 8
            assert regime["historicalAssetMapping"]["assetForecastStatus"] == "blocked"
            assert regime["historicalAssetMapping"]["mappingFramework"]["status"] == "implemented"
            assert regime["jointAssetMapping"]["status"] == "failed"
            assert regime["jointAssetMapping"]["framework"]["status"] == "implemented"
            assert regime["jointAssetMapping"]["exposureRegistry"]["assetCount"] == 98
            assert regime["jointAssetMapping"]["exposureRegistry"]["trackAssetCounts"] == {
                "GLOBAL": 7,
                "CHN": 61,
                "USA": 29,
                "JPN": 0,
                "GBR": 1,
            }
            assert regime["jointAssetMapping"]["cells"]["12mReturn"][
                "exposureValidatedAssetCount"
            ] == 30
            assert regime["jointAssetMapping"]["cells"]["12mReturn"][
                "insufficientCountryHistoryCount"
            ] >= 40
            country_clock = regime["jointAssetMapping"]["countryClockMapping"]
            assert country_clock["status"] == "historical_mapping_only"
            assert country_clock["assetForecastStatus"] == "blocked"
            assert country_clock["lookAhead"] is True
            assert country_clock["summary"]["countryCount"] >= 15
            assert country_clock["summary"]["directAssetCount"] >= 45
            focus = {country["iso"]: country for country in country_clock["focusCountries"]}
            assert focus["CHN"]["status"] == "blocked_short_history"
            assert focus["USA"]["status"] == "direct_long_history"
            assert focus["JPN"]["status"] == "direct_long_history"
            assert focus["GBR"]["status"] == "direct_long_history"
            assert focus["JPN"]["directAssetCount"] == 3
            assert focus["JPN"]["currentPhase"] == "contraction"
            assert len(focus["JPN"]["currentPhaseAssets"]) == 6
            hierarchical_risk = regime["jointAssetMapping"][
                "hierarchicalRiskValidation"
            ]
            assert hierarchical_risk["assetForecastStatus"] == "blocked"
            assert hierarchical_risk["horizonCount"] == 2
            assert set(hierarchical_risk["horizons"]) == {"1y", "3y"}
            assert all(
                horizon["architectures"]["country_hierarchy"]["observations"]
                >= 1_000
                for horizon in hierarchical_risk["horizons"].values()
            )
            assert hierarchical_risk["status"] == "failed"
            asset_class_validation = hierarchical_risk[
                "assetClassValidation"
            ]
            assert asset_class_validation["status"] == "failed"
            assert asset_class_validation["passedTargets"] == 0
            assert asset_class_validation["targetCount"] == 12
            assert {
                asset_class["category"]
                for asset_class in asset_class_validation["classes"]
            } == {"跨国股票", "跨国国债", "跨国短票"}
            assert all(
                asset_class["passedTargets"] == 0
                and asset_class["targetCount"] == 4
                for asset_class in asset_class_validation["classes"]
            )
            conditional = hierarchical_risk[
                "conditionalPropagationValidation"
            ]
            assert conditional["status"] == "failed"
            assert conditional["decision"] == (
                "close_standalone_c2_asset_prediction"
            )
            assert conditional["passedChannels"] == 0
            assert conditional["channelCount"] == 36
            assert conditional["insufficientCoverageChannels"] == 12
            assert {
                scenario["scenarioId"]
                for scenario in conditional["scenarios"]
            } == {
                "high_leverage_financing_easing",
                "housing_downturn_recession",
                "housing_recovery_credit_expansion",
            }
            assert all(
                scenario["passedChannels"] == 0
                and scenario["channelCount"] == 12
                for scenario in conditional["scenarios"]
            )
            assert hierarchical_risk["passedHistoricalRiskChannels"] == 0
            assert "负收益" in hierarchical_risk["riskDefinition"]
            bond_channel = hierarchical_risk["historicalRiskChannels"][0]
            assert bond_channel["channelId"] == (
                "c2_asymmetric_bond_downside_risk_3y"
            )
            assert bond_channel["status"] == "failed"
            assert bond_channel["publicationStatus"] == (
                "rejected_after_risk_definition_audit"
            )
            assert bond_channel["realTimeEligible"] is False
            assert bond_channel["allocationEligible"] is False
            assert bond_channel["assetCategory"] == "跨国国债"
            assert bond_channel["horizonYears"] == 3
            assert bond_channel["riskDefinitionAudit"]["status"] == (
                "failed_after_downside_correction"
            )
            assert bond_channel["recursiveValidation"]["aucDelta"] < 0.01
            assert bond_channel["recursiveValidation"]["brierImprovement"] < 0
            assert bond_channel["macroOnlyValidation"]["status"] == "failed"
            bridge = bond_channel["modernBridge"]
            assert bridge["status"] == "current_macro_state_available"
            assert bridge["structureProxyValidation"]["status"] == "passed_limited"
            assert bridge["modelReplacementValidation"]["status"] == "passed_limited"
            assert bridge["modelReplacementValidation"]["assetMappingEligible"] is False
            assert bridge["currentState"]["status"] == (
                "limited_current_macro_pressure"
            )
            assert bridge["currentState"]["countryCount"] >= 12
            assert bridge["financingProxyValidation"]["status"] == (
                "fidelity_and_current_coverage_passed"
            )
            assert bridge["financingProxyValidation"]["countryCount"] >= 15
            assert bridge["financingProxyValidation"]["correlation"] >= 0.85
            assert bridge["currentState"]["financingCoverage"]["status"] == (
                "current_global_coverage_available"
            )
            assert bridge["currentState"]["financingState"]["countryCount"] >= 12
            assert bond_channel["currentProbabilityStatus"] == (
                "blocked_downside_risk_channel_failed"
            )
            japan_stock_1y = next(
                asset
                for asset in focus["JPN"]["currentPhaseAssets"]
                if asset["category"] == "跨国股票"
                and asset["horizonYears"] == 1
            )
            assert japan_stock_1y["return"]["count"] >= 5
            assert 0 <= japan_stock_1y["return"]["positiveShare"] <= 1
            assert japan_stock_1y["risk"]["mean"] >= 0
            continue
        phase_candidate = cycles["diagnostics"][cycle_id]["phaseCandidate"]
        assert phase_candidate["status"] == "adaptive_phase_candidate"
        assert phase_candidate["validation"]["lookAhead"] is False
        assert phase_candidate["validation"]["meanHistoryAgreement"] > 0.98
        assert phase_candidate["validation"]["dynamicPeriodMedianYears"] > 0
        assert phase_candidate["currentPhaseCandidate"]["status"] in {
            "limited_current_phase_candidate",
            "limited_broad_state_only",
        }
        assert phase_candidate["currentPhaseCandidate"]["asOfPeriod"] == "2026-Q1"
        mixed_frequency = phase_candidate["currentPhaseCandidate"]["validation"]["mixedFrequencyPhase"]
        assert mixed_frequency["status"] == "passed_limited"
        assert mixed_frequency["lookAhead"] is False
        assert mixed_frequency["phaseAccuracy"] >= 0.70
        phase_probability = phase_candidate["currentPhaseCandidate"]["phaseProbability"]
        assert phase_probability["status"] == "passed_limited"
        assert abs(sum(phase_probability["probabilities"].values()) - 1.0) < 1e-5
    c5_state = cycles["diagnostics"]["C5"]["liquidityState"]
    assert c5_state["status"] == "state_direction_predictable"
    assert c5_state["validation"]["3m"]["qualified"] is True
    assert c5_state["validation"]["6m"]["qualified"] is True
    assert c5_state["validation"]["12m"]["qualified"] is True
    assert c5_state["assetValidation"]["status"] == "blocked"
    assert c5_state["assetValidation"]["summary"]["totalChannels"] == 30
    assert len(c5_state["forecastPath"]) == 12
    assert c5_state["current"]["date"] == "2026-06"
    c7_state = cycles["diagnostics"]["C7"]["riskAppetiteState"]
    assert c7_state["status"] == "short_horizon_regime_predictable"
    assert c7_state["validation"]["1m"]["qualified"] is True
    assert c7_state["validation"]["3m"]["qualified"] is True
    assert c7_state["validation"]["6m"]["qualified"] is False
    assert c7_state["pathValidation"]["5m"]["qualified"] is True
    assert len(c7_state["forecastPath"]) == 6
    assert c7_state["assetValidation"]["status"] == "blocked"
    assert c7_state["assetValidation"]["summary"]["totalChannels"] == 30
    assert len(c7_state["assetValidation"]["cells"]) == 15
    assert c7_state["current"]["date"] == "2026-07"
    expected_horizons = {
        "C2": {12, 24, 36},
        "C3": {12, 24, 36},
        "C5": {3, 6, 12},
        "C7": {1, 2, 3, 4, 5},
    }
    for cycle_id, horizons in expected_horizons.items():
        publication = cycles["diagnostics"][cycle_id]["directionPublication"]
        assert publication["status"] == "limited"
        assert publication["exactCycleStatus"] == "blocked"
        assert publication["assetForecastStatus"] == "blocked"
        assert publication["gate"]["passed"] is True
        assert publication["gate"]["reasonCodes"] == []
        assert {row["months"] for row in publication["horizons"]} == horizons
        assert all(row["qualified"] for row in publication["horizons"])

    assets = json.loads(outputs["assets"].read_text(encoding="utf-8"))
    assert assets["meta"]["generated"] == market["meta"]["generated"]
    assert assets["meta"]["generated"] == cycles["meta"]["generated"]
    assert assets["meta"]["historicalStatisticsGenerated"] == "2026-07-22"
    assert assets["meta"]["historicalStatisticsAsOf"] == "2026-06"
    assert assets["meta"]["forecastAsOf"] == "2026-07"
    assert assets["meta"]["forecastAssetDataThrough"] == "2026-07"
    assert assets["publication"]["C4"] == "formal"
    assert assets["publication"]["C2"] == "blocked"
    assert assets["summary"]["observed_assets"] == 98
    assert assets["summary"]["unavailable_assets"] == 0
    commodity_names = {
        row["name"] for row in assets["assets"] if row["category"] == "商品"
    }
    assert {"黄金", "铜", "原油", "中国大宗商品价格综合指数"} <= commodity_names
    assert any(
        row["category"] == "外汇" and row["name"] == "美元指数DXY"
        for row in assets["assets"]
    )
    assert set(assets["researchMappings"]) == {"C2", "C3"}
    assert assets["researchMappings"]["C2"]["assetMapping"]["summary"]["eligibleAssets"] >= 120
    assert assets["researchMappings"]["C3"]["assetMapping"]["summary"]["eligibleAssets"] >= 130
    for cycle_id in ("C2", "C3"):
        mapping = assets["researchMappings"][cycle_id]["assetMapping"]
        if cycle_id == "C2":
            assert "currentProbabilityWeightedScenario" not in mapping
            assert mapping["assetForecastStatus"] == "blocked"
            assert mapping["mappingFramework"]["status"] == "implemented"
            current_direction = assets["researchMappings"][cycle_id]["currentDirection"]
            assert current_direction["regimeState"]["phase"] == "contraction"
            assert current_direction["assetForecastStatus"] == "blocked"
            continue
        assert "currentProbabilityWeightedScenario" not in mapping
        assert mapping["status"] == "legacy_mapping_rebuild_required"
        assert mapping["assetForecastStatus"] == "blocked"
        assert "双核心" in mapping["caveat"]
        current_direction = assets["researchMappings"][cycle_id]["currentDirection"]
        assert current_direction["assetForecastStatus"] == "blocked"
        assert current_direction["currentForecasts"][0]["asOfPeriod"] == "2026-Q1"
        current_phase = current_direction["currentPhaseCandidate"]
        assert current_phase["status"] == "limited_current_phase_candidate"
        assert current_phase["current"]["phase"] == "recovery"
        assert current_phase["parameterRobustness"]["status"] == "stable_band"
        assert current_phase["parameterRobustness"]["periodRangeYears"] == [
            10.125,
            10.125,
        ]
        asset_validation = assets["researchMappings"][cycle_id]["assetValidation"]
        assert asset_validation["status"] == "failed"
        assert asset_validation["passedTargets"] == 1
        assert asset_validation["targetCount"] == 8
        assert sum(cell["passed"] for cell in asset_validation["cells"]) == 1
    c2_research = assets["researchMappings"]["C2"]
    assert c2_research["geographicState"]["summary"]["regionCount"] == 4
    assert {
        row["iso"] for row in c2_research["geographicState"]["focusCountries"]
    } == {"CHN", "USA", "JPN", "GBR"}
    focus_countries = {
        row["iso"]: row
        for row in c2_research["geographicState"]["focusCountries"]
    }
    assert focus_countries["CHN"]["historyTier"] == "modern_quarterly_short"
    assert focus_countries["USA"]["historyTier"] == "modern_quarterly_direct"
    assert focus_countries["JPN"]["historyTier"] == "modern_quarterly_direct"
    assert focus_countries["GBR"]["historyTier"] == "modern_quarterly_direct"
    geographic_validation = c2_research["assetMapping"]["geographicValidation"]
    assert geographic_validation["status"] == "failed"
    assert geographic_validation["commonEligibleAssets"] >= 110
    assert all(
        candidate["passedCells"] == 0
        for candidate in geographic_validation["candidates"]
    )
    assert c2_research["assetMapping"]["interactionValidation"]["status"] == (
        "not_run_geographic_gate_failed"
    )
    assert assets["stateDiagnostics"]["C5"]["status"] == "state_direction_predictable"
    assert assets["stateDiagnostics"]["C5"]["governance"]["assetForecastStatus"] == "blocked"
    assert assets["stateDiagnostics"]["C7"]["status"] == "short_horizon_regime_predictable"
    assert assets["stateDiagnostics"]["C7"]["governance"]["assetForecastStatus"] == "blocked"
    assert set(assets["stateMappings"]) == {"C5", "C7"}
    assert assets["stateMappings"]["C5"]["summary"]["positiveOosR2"] >= 10
    assert assets["stateMappings"]["C7"]["summary"]["positiveOosR2"] >= 15
    assert assets["stateMappings"]["C5"]["currentState"]["assetForecastStatus"] == "blocked"
    assert assets["stateMappings"]["C7"]["currentState"]["assetForecastStatus"] == "blocked"
    assert assets["stateMappings"]["C7"]["currentState"]["qualifiedDirectionHorizons"] == [
        "1m",
        "2m",
        "3m",
        "4m",
        "5m",
    ]
    current_forecast = assets["currentCycleForecast"]
    assert current_forecast["meta"]["asOf"] == "2026-07"
    assert current_forecast["meta"]["forecastClock"] == "asynchronous_release_clock"
    assert current_forecast["meta"]["modelVersion"] == (
        "asset_cycle_state_v8_cycle_shapley"
    )
    assert current_forecast["meta"]["modelPolicies"]["6"] == (
        "fixed_state_analog_shrunk"
    )
    assert {
        row["cycleId"]: row["observationUsed"]
        for row in current_forecast["meta"]["stateClock"]["cycles"]
    } == {"C4": "2026-06", "C5": "2026-06", "C7": "2026-07"}
    assert current_forecast["clockComparison"]["status"] == (
        "paired_recent_nested_oos"
    )
    assert current_forecast["meta"]["layer"] == "joint_state_forecast"
    assert current_forecast["meta"]["includedCycles"] == ["C4", "C5", "C7"]
    assert current_forecast["meta"]["attributionStability"]["assets"] == 10
    assert current_forecast["meta"]["separateFromSingleCycleMapping"] is True
    assert current_forecast["summary"]["refreshedAssets"] == 81
    assert current_forecast["summary"]["sourceLagAssets"] == 17
    assert current_forecast["summary"]["staleAssets"] == 0
    assert current_forecast["summary"]["horizons"]["1"]["fullSampleQualifiedAssets"] > 0
    assert (
        current_forecast["summary"]["horizons"]["1"]["qualifiedAssets"]
        <= current_forecast["summary"]["horizons"]["1"]["fullSampleQualifiedAssets"]
    )
    assert current_forecast["summary"]["horizons"]["3"]["qualifiedAssets"] == 2
    assert {
        asset["name"]
        for asset in current_forecast["assets"]
        if asset["horizons"]["3"]["publicationQualified"]
    } == {"原油", "石油石化"}
    assert current_forecast["summary"]["horizons"]["6"]["qualifiedAssets"] == 7
    assert all(
        asset["horizons"]["6"].get("synchronousReferenceStable")
        for asset in current_forecast["assets"]
        if asset["horizons"]["6"]["publicationQualified"]
    )

    audit = json.loads(outputs["audit"].read_text(encoding="utf-8"))
    source_rows = {row["entity"]: row for row in audit["sources"]}
    assert source_rows["C5/C7 当前状态增量刷新"]["asOf"] == "2026-07"
    assert source_rows["C2/C3 长历史方向验证"]["asOf"] == "2026-Q1"
    assert source_rows["现实资产收益增量刷新"]["asOf"] == "2026-07"
    assert source_rows["逐资产周期状态条件预测"]["asOf"] == "2026-07"

    market = json.loads(outputs["market"].read_text(encoding="utf-8"))
    default_tracks = [
        track for track in market["tracks"]
        if track["id"] in market["meta"]["defaultTrackIds"]
    ]
    assert len(default_tracks) == len(market["meta"]["defaultTrackIds"])
    assert all(
        track["forecast"]["status"] in {"limited", "blocked"}
        for track in default_tracks
    )
    qualified_default_tracks = [
        track for track in default_tracks if track["forecast"]["status"] == "limited"
    ]
    assert len(qualified_default_tracks) >= 9
    assert all(track["forecast"]["dates"] for track in qualified_default_tracks)
    assert all(
        track["forecast"]["dates"][0] > track["coverage"]["end"]
        for track in qualified_default_tracks
    )

    forecast = json.loads(outputs["forecast"].read_text(encoding="utf-8"))
    assert forecast["qualifiedModels"] == ["ridge"]
    assert forecast["eligibility"]["C4"] == "forecast_candidate"
    assert len(forecast["assetConditionalForecasts"]) == 98
    assert {row["status"] for row in forecast["assetConditionalForecasts"]} == {
        "limited"
    }
