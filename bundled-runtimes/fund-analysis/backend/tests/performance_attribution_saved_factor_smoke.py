import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.performance_attribution_service import PerformanceAttributionService


class FundRepo:
    def get_fund_by_identifier(self, wind_code):
        return {"wind_code": wind_code, "name": "测试基金", "type": "股票型", "raw_data": {}}


class HoldingRepo:
    def get_holdings(self, _wind_code, _quarter):
        return [{
            "stock_code": "600000.SH",
            "industry": "银行",
            "weight": 0.3,
            "weight_basis": "fund_nav",
        }]


class FactorRepo:
    def get_exposures(self, _wind_code, _quarter):
        return [{"factor_name": "SIZE", "exposure": 0.4, "risk_contribution": None}]


class HoldingStyleSnapshotRepo:
    def get(self, _wind_code, _quarter):
        return None


class ClassificationRepo:
    def get_classification_context(self, _wind_code):
        return {}


class DataService:
    mock_mode = False


class InvestmentAnalysis:
    def factor_lens(self, *_args, **_kwargs):
        return {"status": "ok", "missing_items": []}

    def advanced_attribution(self, *_args, **_kwargs):
        return {"status": "insufficient_evidence", "missing_items": []}


def main():
    service = PerformanceAttributionService(classification_adapter=ClassificationRepo())
    with (
        patch("repositories.get_fund_repo", return_value=FundRepo()),
        patch("repositories.get_holding_repo", return_value=HoldingRepo()),
        patch("repositories.get_factor_repo", return_value=FactorRepo()),
        patch("repositories.get_holding_style_snapshot_repo", return_value=HoldingStyleSnapshotRepo()),
        patch("repositories.get_attribution_repo") as attribution_repo,
        patch("service_registry.get_data_service", return_value=DataService()),
        patch("services.investment_analysis_service.InvestmentAnalysisService", InvestmentAnalysis),
    ):
        attribution_repo.return_value.save_bundle.return_value = True
        result = service.analyze("000001.OF", quarter="2026Q2")

    barra = result["barra"]
    assert barra["source"] == "local_postgres.factor_exposures", barra
    assert barra["factor_exposures"] == [{
        "factor": "SIZE",
        "exposure": 0.4,
        "risk_contribution": None,
    }], barra
    assert barra["industry_exposures"] == {"银行": 0.3}, barra
    print("OK live attribution reuses saved Barra factors without heavy external descriptor calls")


if __name__ == "__main__":
    main()
