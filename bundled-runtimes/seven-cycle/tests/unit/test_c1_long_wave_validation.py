from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research_c1_long_wave_validation import build_validation


def test_c1_validation_rejects_fixed_wave_publication() -> None:
    payload = build_validation(simulations=20)

    assert payload["dates"][-1] == "2024"
    assert payload["frequencyValidation"]["familyCount"] == 7
    assert set(payload["familySeries"]) == {
        "全球产出",
        "全球生产率",
        "技术扩散",
        "资本形成",
        "劳动人口",
        "全球连接",
        "全球能源系统",
    }
    assert len(payload["longWave"]) == len(payload["dates"])
    assert "scenarioWave" not in payload
    assert "phaseAngle" not in payload
    assert all(row["nonOverlappingOrigins"] for row in payload["directionValidation"])
    assert payload["directionConsensus"]["status"] == "blocked"
    assert payload["directionConsensus"]["qualifiedHorizonsYears"] == [5]
    assert payload["directionConsensus"]["crossHorizonAgreement"] is False
    assert "通过检验的长期方向辅助判断" not in payload["publication"]["allowedUses"]
    assert "精确峰谷年份" in payload["publication"]["blockedUses"]
    assert payload["currentState"]["levelLabel"] == "位置未校准"
    assert payload["phaseCalibration"]["phase"] == "萧条末期"
    assert payload["phaseCalibration"]["quantitativelyValidated"] is False
    assert payload["frequencyValidation"]["bandYears"] == [35.0, 70.0]
    assert payload["coreCoverage"]["currentRatio"] >= 0.7
    assert payload["coreCoverage"]["currentBridgeRatio"] > 0
    assert payload["coreCoverage"]["currentDirectRatio"] < payload["coreCoverage"]["currentRatio"]
    technology = next(
        row for row in payload["familyCoverage"] if row["family"] == "技术扩散"
    )
    assert technology["bridgeStatus"] == "rejected"
    assert technology["bridgeOverlapYears"] == 9
    assert technology["bridgeOverlapCorrelation"] < technology["bridgeMinimumCorrelation"]
    assert technology["end"] == 2003
    assert payload["globalProxyAssessment"]["proxies"]["ukGdpPerCapita"]["bandCorrelation"] < 0
    assert payload["financialValidation"]["available"] is True
    assert payload["strategicAllocationGuidance"]["status"] == "blocked"
    assert "独立资产配置权重" in payload["publication"]["blockedUses"]
