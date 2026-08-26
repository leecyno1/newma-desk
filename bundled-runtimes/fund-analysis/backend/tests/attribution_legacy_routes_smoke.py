import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import barra, brinson  # noqa: E402


class FakeAttributionService:
    calls = []

    def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "fund": {"wind_code": "000001.OF", "name": "测试基金", "type": "stock"},
            "status": "partial_evidence",
            "quarter": "2026Q2",
            "holding_snapshot_quarter": "2026Q1",
            "benchmark": "000905.SH",
            "benchmark_source": "fund_classification_catalog",
            "barra": {
                "status": "partial_evidence",
                "source": "factor_exposure_input",
                "formal_model_ready": False,
                "quarter": "2026Q1",
                "factor_exposures": [{"factor": "SIZE", "exposure": 0.4}],
                "industry_exposures": {"电子": 0.2},
                "risk_contributions": [],
                "r_squared": None,
                "holdings_count": 10,
                "holdings_disclosed_weight": 0.63,
                "missing_items": ["缺少正式协方差矩阵"],
            },
            "brinson": {
                "status": "partial_evidence",
                "source": "tushare.real_inputs",
                "returns": {"fund": 0.05, "benchmark": 0.03, "active": 0.02},
                "effects": [
                    {"name": "allocation", "value": 0.006},
                    {"name": "selection", "value": 0.009},
                    {"name": "interaction", "value": 0.001},
                    {"name": "residual", "value": 0.004},
                ],
                "industry_detail": [{"industry": "电子"}],
                "coverage": {"portfolio_holdings": 0.63},
                "missing_items": ["持仓披露不完整"],
            },
        }


def main() -> int:
    FakeAttributionService.calls = []
    target = "services.performance_attribution_service.PerformanceAttributionService"
    with patch(target, FakeAttributionService):
        exposure = asyncio.run(barra.get_barra_exposure("000001.OF", quarter="2026Q2"))
        risk = asyncio.run(barra.get_risk_decomposition("000001.OF", quarter="2026Q2"))
        attribution = asyncio.run(
            brinson.get_brinson_attribution("000001.OF", benchmark=None, quarter="2026Q2")
        )

    if exposure["r_squared"] is not None or exposure["specific_risk"] is not None:
        raise AssertionError("Legacy Barra route must not fabricate R² or specific risk")
    if exposure["risk_contributions"] or exposure["total_factor_risk"] is not None:
        raise AssertionError("Legacy Barra route must not fabricate factor risk contributions")
    if risk["factor_risk"] is not None or risk["specific_risk_pct"] is not None:
        raise AssertionError("Legacy risk decomposition must remain unavailable without formal risk inputs")
    if attribution["benchmark"] != "000905.SH" or attribution["benchmark_source"] != "fund_classification_catalog":
        raise AssertionError("Legacy Brinson route must preserve the classified benchmark")
    if attribution["returns"]["portfolio"] != 0.05 or attribution["attribution"]["total"] != 0.02:
        raise AssertionError("Legacy Brinson route mapped the unified result incorrectly")
    if FakeAttributionService.calls[-1]["benchmark"] is not None:
        raise AssertionError("Empty legacy benchmark must not override the classification catalog")

    history = asyncio.run(brinson.get_brinson_history("000001.OF", quarters=8))
    if history["status"] != "deprecated" or history["attributions"]:
        raise AssertionError("Legacy Brinson history must not fabricate quarterly records")

    backend = Path(__file__).resolve().parents[1]
    route_source = (backend / "routes" / "barra.py").read_text(encoding="utf-8") + (
        backend / "routes" / "brinson.py"
    ).read_text(encoding="utf-8")
    model_source = (backend / "lib" / "barra" / "factor_calculation.py").read_text(encoding="utf-8") + (
        backend / "lib" / "brinson" / "attribution.py"
    ).read_text(encoding="utf-8")
    for forbidden in [
        "BarraCalculator",
        "save_exposures",
        "fund_return * 0.25",
        "BENCHMARK_INDUSTRY_WEIGHTS",
        "def calculate_attribution(",
        "specific_var: float = 0.02",
    ]:
        if forbidden in route_source or forbidden in model_source:
            raise AssertionError(f"Legacy attribution still contains fabricated methodology: {forbidden}")

    print("OK legacy Barra and Brinson routes use unified real-data attribution only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
