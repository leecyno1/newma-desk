import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.professional_scoring_service import ProfessionalScoringService


class _Classification:
    def classify(self, fund, profile, standardized):
        return {
            "status": "classified",
            "strategy_family_key": "fof_balanced_allocation",
            "evaluation_profile_key": "fof_balanced",
            "peer_group": "FOF-平衡配置",
            "primary_benchmark": "FOF 合同基准权益权重>30%且<60%",
            "missing_items": [],
        }


class _Lookthrough:
    def __init__(self, sufficient=True):
        self.sufficient = sufficient

    def get(self, wind_code, refresh=False):
        return {
            "status": "available" if self.sufficient else "unavailable",
            "evidence_gate": {
                "status": "sufficient" if self.sufficient else "insufficient_evidence",
                "disclosed_fund_count": 8 if self.sufficient else 0,
                "disclosed_nav_ratio": 36.0 if self.sufficient else 0.0,
                "missing_items": [] if self.sufficient else ["FOF 底层基金穿透证据不足"],
            },
            "professional_profile": {"top5_nav_ratio": 24.0},
            "missing_items": [],
        }


def _panel():
    values = {
        "annualized_return": 0.07,
        "max_drawdown": -0.08,
        "sharpe_ratio": 0.9,
        "annualized_volatility": 0.11,
        "positive_return_ratio": 0.58,
    }
    return [
        {"metric_window": "1y", "metric_name": key, "metric_value": value, "as_of_date": "2026-08-13"}
        for key, value in values.items()
    ]


def main() -> int:
    fund = {"wind_code": "FOF.TEST", "establishment_date": "2020-01-01"}
    quality = {"score": 90, "issues": [], "status": "complete"}

    scoring = ProfessionalScoringService(
        classification_service=_Classification(),
        fof_holding_service=_Lookthrough(sufficient=True),
    ).score_from_inputs(fund, {}, _panel(), quality)
    if scoring.get("status") not in {"ok", "partial"} or scoring.get("overall_score") is None:
        raise AssertionError(scoring)
    if scoring.get("fund_type_profile") != "fof_balanced":
        raise AssertionError(scoring)
    if not scoring.get("fof_lookthrough"):
        raise AssertionError(scoring)

    blocked = ProfessionalScoringService(
        classification_service=_Classification(),
        fof_holding_service=_Lookthrough(sufficient=False),
    ).score_from_inputs(fund, {}, _panel(), quality)
    if blocked.get("status") != "insufficient_evidence" or blocked.get("overall_score") is not None:
        raise AssertionError(blocked)
    if "FOF 底层基金穿透证据不足" not in (blocked.get("missing_data") or []):
        raise AssertionError(blocked)

    print("OK FOF scoring uses a dedicated profile and blocks without lookthrough evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
