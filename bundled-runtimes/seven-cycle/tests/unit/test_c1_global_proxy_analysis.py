from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research_c1_global_proxy_analysis import build_analysis


def test_c1_global_proxy_analysis_separates_core_and_assets() -> None:
    payload = build_analysis()

    assessment = payload["longSampleProxyAssessment"]
    assert assessment["countryCount"] >= 10
    assert assessment["proxies"]["ukGdpPerCapita"]["effectiveLongWaves"] < 8
    assert assessment["proxies"]["ukCpiInflation"]["bandCorrelation"] < 0.3
    assert "股票" not in payload["recommendedArchitecture"]["coreIdentification"]
    assert "股票、住房、债券与商品价格" in payload["recommendedArchitecture"]["financialValidation"]
