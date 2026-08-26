from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_c2_c3_historical_mapping import OUTPUT_PATH, PHASE_LABELS


def test_generated_historical_phase_and_asset_mapping_is_governed() -> None:
    assert OUTPUT_PATH.exists()
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))

    assert payload["meta"]["phaseLabels"] == PHASE_LABELS
    assert set(payload["cycles"]) == {"C2", "C3"}
    for cycle_id, cycle in payload["cycles"].items():
        assert cycle["status"] == "adaptive_phase_candidate"
        assert cycle["formalStatus"] == "blocked"
        assert cycle["validation"]["lookAhead"] is False
        assert "不代表相位预测准确率" in cycle["validation"]["appendOnlyStabilityDefinition"]
        assert cycle["validation"]["meanHistoryAgreement"] > 0.98
        assert cycle["validation"]["dynamicPeriodMedianYears"] > 0
        assert len(cycle["validation"]["dynamicPeriodIqrYears"]) == 2
        assert cycle["validation"]["latestPhaseAgreement"] >= 0.5
        assert len(cycle["history"]) >= 120
        assert set(cycle["phaseCounts"]) == set(PHASE_LABELS)
        assert sum(cycle["phaseCounts"].values()) == len(cycle["history"])

        current_phase = cycle["currentPhaseCandidate"]
        assert current_phase["status"] in {
            "limited_current_phase_candidate",
            "limited_broad_state_only",
        }
        assert current_phase["asOfPeriod"] == "2026-Q1"
        assert current_phase["current"]["phase"] in PHASE_LABELS
        assert current_phase["current"]["periodYears"] > 0
        assert 0 <= current_phase["current"]["periodBoundaryShare"] <= 1
        assert 0 <= current_phase["current"]["periodSelectionStrength"] <= 1
        identification = current_phase["periodIdentification"]
        assert identification["status"] in {
            "boundary_unresolved",
            "family_disagreement",
            "weakly_identified",
            "limited_candidate",
        }
        assert identification["conclusion"]
        assert current_phase["validation"]["phaseAgreement"] >= 0.55
        assert current_phase["validation"]["directionAgreement"] >= 0.65
        family_confirmation = current_phase["validation"]["familyConfirmation"]
        assert family_confirmation["currentFamilyCount"] >= 3
        assert family_confirmation["staleFamilyCount"] >= 0
        if cycle_id == "C2":
            assert family_confirmation["aggregatePhaseAgreement"] < 2 / 3
            assert family_confirmation["aggregateSlopeAgreement"] < 2 / 3
            assert family_confirmation["aggregateLevelAgreement"] >= 2 / 3
        else:
            assert family_confirmation["aggregatePhaseAgreement"] >= 0.50
            assert family_confirmation["aggregateSlopeAgreement"] >= 0.50
        assert len(family_confirmation["periodIqrYears"]) == 2
        assert all("lagYears" in row for row in family_confirmation["families"])
        family_ablation = current_phase["validation"]["familyAblationPhase"]
        assert family_ablation["tests"] >= 4
        assert family_ablation["phaseAgreement"] >= 0.40
        assert family_ablation["levelAgreement"] >= 0.50
        assert family_ablation["slopeAgreement"] >= 0.50
        assert "重新完成跨源尺度校准" in family_ablation["definition"]
        broad_state = current_phase["governedBroadState"]
        assert broad_state["status"] == "limited_broad_state"
        assert broad_state["level"] == "below_trend"
        assert broad_state["momentum"] in {"rising", "falling", "mixed"}
        assert broad_state["levelAgreement"] >= 2 / 3
        mixed_frequency = current_phase["validation"]["mixedFrequencyPhase"]
        assert mixed_frequency["status"] == "passed_limited"
        assert mixed_frequency["lookAhead"] is False
        assert mixed_frequency["endYear"] <= 2025
        assert mixed_frequency["phaseAccuracy"] >= 0.70
        assert mixed_frequency["levelDirectionAccuracy"] >= 0.80
        assert mixed_frequency["slopeDirectionAccuracy"] >= 0.75
        for key, point_key in (
            ("phaseAccuracyInterval90", "phaseAccuracy"),
            ("levelDirectionAccuracyInterval90", "levelDirectionAccuracy"),
            ("slopeDirectionAccuracyInterval90", "slopeDirectionAccuracy"),
        ):
            assert mixed_frequency[key][0] <= mixed_frequency[point_key] <= mixed_frequency[key][1]
        if cycle_id == "C2":
            assert mixed_frequency["broadStateValidation"]["status"] == "passed_limited"
        else:
            assert mixed_frequency["broadStateValidation"]["status"] in {
                "passed_limited",
                "failed",
            }
        assert mixed_frequency["transitionPhaseAccuracyInterval90"][1] - mixed_frequency["transitionPhaseAccuracyInterval90"][0] > 0.30
        phase_probability = current_phase["phaseProbability"]
        if cycle_id == "C2":
            assert current_phase["status"] == "limited_broad_state_only"
            assert current_phase["exactPhaseStatus"] == "blocked"
            assert broad_state["momentum"] == "mixed"
            assert phase_probability["status"] == "blocked_current_disagreement"
            assert phase_probability["publishable"] is False
            robustness = current_phase["periodRobustness"]
            assert robustness["status"] == "period_band_only"
            assert robustness["periodRangeYears"][0] < robustness["periodRangeYears"][1]
            assert robustness["periodRangeYears"] == current_phase[
                "periodIdentification"
            ]["candidateRangeYears"]
            assert robustness["boundaryFreeShare"] == 1.0
        else:
            assert phase_probability["status"] == "passed_limited"
            assert phase_probability["publishable"] is True
        assert phase_probability["primaryPhase"] == current_phase["current"]["phase"]
        assert phase_probability["primaryProbability"] > phase_probability["alternativeProbability"]
        assert abs(sum(phase_probability["probabilities"].values()) - 1.0) < 1e-5
        assert phase_probability["validation"]["multiclassBrier"] <= phase_probability["validation"]["hardMulticlassBrier"]

        mapping = cycle["assetMapping"]
        assert mapping["status"] == "research_mapping_candidate"
        assert mapping["summary"]["eligibleAssets"] >= (
            120 if cycle_id == "C2" else 130
        )
        assert mapping["summary"]["positiveOosR2"] > 0
        identities = {asset["dataIdentity"] for asset in mapping["assets"]}
        assert identities == {
            "direct_historical_series",
            "official_research_portfolio_proxy",
        }
        assert all(asset["caveat"] for asset in mapping["assets"])
        if cycle_id == "C2":
            housing_assets = [
                asset
                for asset in mapping["assets"]
                if asset["category"] == "跨国住房"
            ]
            assert housing_assets
            assert not any(asset["eligible"] for asset in housing_assets)
            assert all(asset["exclusionReason"] for asset in housing_assets)
            forward = mapping["summary"]["forwardValidation"]
            assert forward["status"] == "failed"
            assert mapping["summary"]["hacFdrPassed"] == 0
            for validation_id in ("1yReturn", "3yReturn", "1yRisk", "3yRisk"):
                assert forward[validation_id]["assets"] >= 120
                assert forward[validation_id]["positiveOosR2Share"] < 0.50
                assert forward[validation_id]["medianOosR2"] < 0
            geographic_state = cycle["geographicState"]
            assert geographic_state["status"] == "research_only"
            assert geographic_state["formalStatus"] == "blocked"
            assert geographic_state["asOfPeriod"] == "2026-Q1"
            assert geographic_state["summary"]["countryCount"] >= 15
            assert geographic_state["summary"]["regionCount"] == 3
            assert len(geographic_state["currentRegions"]) == 3
            assert geographic_state["summary"][
                "countryPhaseAgreementWithGlobal"
            ] < 2 / 3
            geographic_validation = mapping["geographicValidation"]
            assert geographic_validation["status"] == "failed"
            assert geographic_validation["lookAhead"] is False
            assert geographic_validation["commonEligibleAssets"] >= 110
            assert all(
                candidate["passedCells"] == 0
                for candidate in geographic_validation["candidates"]
            )
            for cell in geographic_validation["cells"].values():
                assert set(cell["models"]) == {
                    "global",
                    "region",
                    "country",
                    "countryLagged",
                    "decomposition",
                }
                assert all(
                    model["medianOosR2"] < 0
                    for model in cell["models"].values()
                )
            assert mapping["interactionValidation"]["status"] == (
                "not_run_geographic_gate_failed"
            )
            assert len(
                mapping["interactionValidation"]["preregisteredCandidates"]
            ) == 3
        scenario = mapping["currentProbabilityWeightedScenario"]
        assert scenario["status"] == (
            "blocked_current_phase_disagreement"
            if cycle_id == "C2"
            else "passed_vs_hard_phase_only"
        )
        assert scenario["assetForecastStatus"] == "blocked"
        assert scenario["summary"]["assets"] == (0 if cycle_id == "C2" else len(scenario["assets"]))
        assert scenario["validation"]["assetShareBeatingHardPhase"] >= 0.75
        assert scenario["validation"]["assetShareBeatingUnconditional"] < 0.50
        assert scenario["validation"]["positiveOosR2Share"] < 0.50
        risk_validation = scenario["validation"]["risk"]
        assert risk_validation["phaseWeight"] in {0.0, 0.10, 0.25}
        selected_error = risk_validation["weightSelection"]["maeByWeight"][
            str(risk_validation["phaseWeight"])
        ]
        assert selected_error == min(
            risk_validation["weightSelection"]["maeByWeight"].values()
        )
        assert risk_validation["weightSelection"]["endYear"] == 2020
        assert risk_validation["holdout"]["startYear"] == 2021
        assert risk_validation["holdout"]["endYear"] == 2025
        assert risk_validation["holdout"]["years"] == 5
        assert risk_validation["holdout"]["assets"] >= 70
        if cycle_id == "C2":
            assert scenario["riskForecastStatus"] == "blocked"
            assert risk_validation["maeImprovementVsUnconditional"] <= 0.005
            assert risk_validation["yearBlockBootstrapProbability"] < 0.90
        else:
            assert scenario["riskForecastStatus"] == "blocked"
            assert risk_validation["yearBlockBootstrapProbability"] < 0.90
        assert len(scenario["assets"]) == scenario["summary"]["assets"]
        assert all(asset["conditionalAnnVol"] >= 0 for asset in scenario["assets"])
        assert all(asset["governedRiskScale"] >= 0 for asset in scenario["assets"])
        if cycle_id == "C2":
            assert scenario["assets"] == []
        else:
            assert sum(
                asset["riskValidationEligible"] for asset in scenario["assets"]
            ) >= 70

    probability_calibration = payload["phaseProbabilityCalibration"]
    assert probability_calibration["status"] == "passed_limited"
    assert probability_calibration["lookAhead"] is False
    assert probability_calibration["pooledValidation"]["relativeBrierImprovement"] >= 0.10
    assert probability_calibration["pooledValidation"]["top1Accuracy"] >= probability_calibration["pooledValidation"]["hardTop1Accuracy"]
