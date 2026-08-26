import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.peer_comparison_service import PeerComparisonService


class FakeFundRepo:
    def __init__(self, funds: dict[str, dict]):
        self.funds = funds

    def get_fund_by_identifier(self, wind_code: str):
        return self.funds.get(wind_code)


class FakeProfileRepo:
    def __init__(self, profiles: dict[str, dict]):
        self.profiles = profiles

    def get_profile(self, wind_code: str):
        return self.profiles.get(wind_code)

    def list_profiles(self, wind_codes: list[str]):
        return {code: self.profiles.get(code, {}) for code in wind_codes}


class LegacyFallbackClassificationAdapter:
    def get_classification_context(self, wind_code: str):
        return {"status": "schema_unavailable", "fund_code": wind_code, "missing_items": []}


class TestPeerComparisonService(PeerComparisonService):
    def __init__(self, funds: dict[str, dict], profiles: dict[str, dict], profile_peers=None, type_peers=None):
        super().__init__(
            classification_adapter=LegacyFallbackClassificationAdapter(),
            fund_repo=FakeFundRepo(funds),
            profile_repo=FakeProfileRepo(profiles),
        )
        self.profile_peers = profile_peers or []
        self.type_peers = type_peers or []
        self.requested_types = []

    def _query_peer_funds_by_profile(self, peer_group: str):
        return list(self.profile_peers)

    def _query_peer_funds_by_types(self, fund_types: list[str]):
        self.requested_types = list(fund_types)
        return list(self.type_peers)


def main() -> int:
    unknown_service = TestPeerComparisonService(
        {"UNKNOWN.TEST": {"wind_code": "UNKNOWN.TEST", "name": "无法识别产品", "type": "其他"}},
        {},
        type_peers=[{"wind_code": "STOCK.TEST", "name": "股票基金", "type": "stock"}],
    )
    unknown_target, unknown_peers, unknown_source = unknown_service._peer_universe("UNKNOWN.TEST")
    if unknown_source != "classification_insufficient_evidence":
        raise AssertionError(f"Unknown classification must stop peer fallback: {unknown_source}")
    if [fund.get("wind_code") for fund in unknown_peers] != ["UNKNOWN.TEST"]:
        raise AssertionError(f"Unknown fund must not borrow a broad peer bucket: {unknown_peers}")
    if unknown_service.requested_types:
        raise AssertionError(f"Unknown fund must not query arbitrary types: {unknown_service.requested_types}")
    if unknown_target.get("classification", {}).get("status") != "insufficient_evidence":
        raise AssertionError(f"Peer result must retain classification evidence: {unknown_target}")

    index_service = TestPeerComparisonService(
        {"INDEX.TEST": {"wind_code": "INDEX.TEST", "name": "沪深300ETF联接A", "type": "指数型"}},
        {},
        type_peers=[
            {"wind_code": "INDEX.PEER", "name": "中证500ETF联接A", "type": "指数型"},
        ],
    )
    index_target, _, index_source = index_service._peer_universe("INDEX.TEST")
    if index_source != "classification_fund_type_fallback":
        raise AssertionError(f"Index fallback must be classification-driven: {index_source}")
    requested = set(index_service.requested_types)
    if not requested.intersection({"index", "指数型", "被动指数型"}):
        raise AssertionError(f"Index-compatible types missing: {requested}")
    if requested.intersection({"stock", "股票型", "hybrid", "混合型"}):
        raise AssertionError(f"Index fallback leaked equity types: {requested}")
    if index_target.get("classification", {}).get("strategy_family_key") != "index_broad":
        raise AssertionError(f"Index classification must reach peer evaluation: {index_target}")

    unsupported_index_score = index_service._fast_peer_score(
        {"annualized_return": 0.12, "max_drawdown": -0.10, "sharpe_ratio": 1.2},
        "index_fund",
    )
    if unsupported_index_score is not None:
        raise AssertionError(f"Index fund must not reuse active-equity proxy score: {unsupported_index_score}")

    index_score_map = index_service._fast_peer_score_map(
        ["INDEX.TEST"],
        {
            "INDEX.TEST": {
                "1y": {"tracking_error": 0.006, "excess_return": -0.004},
                "latest": {"expense_ratio": 0.006, "aum": 45.0},
            },
        },
        "1y",
        "index_fund",
    )
    if index_score_map["INDEX.TEST"]["overall_score"] is None:
        raise AssertionError(f"Index peer proxy must combine window and latest facts: {index_score_map}")

    money_score_map = index_service._fast_peer_score_map(
        ["MONEY.TEST"],
        {
            "MONEY.TEST": {
                "1y": {
                    "annualized_return": 0.021,
                    "max_drawdown": -0.0004,
                    "annualized_volatility": 0.0018,
                    "positive_return_ratio": 0.99,
                },
                "latest": {"seven_day_annualized_yield": 0.019, "aum": 120.0},
            },
        },
        "1y",
        "money_market",
    )
    if money_score_map["MONEY.TEST"]["overall_score"] is None:
        raise AssertionError(f"Money-market peer proxy must combine window and latest facts: {money_score_map}")

    fixed_income_score = index_service._fast_peer_score(
        {
            "annualized_return": 0.045,
            "max_drawdown": -0.025,
            "annualized_volatility": 0.035,
            "sharpe_ratio": 1.1,
            "positive_return_ratio": 0.60,
        },
        "fixed_income",
    )
    if fixed_income_score is None:
        raise AssertionError("Supported fixed-income category should have a category-specific peer proxy")

    print("OK peer comparison uses classification-compatible peers and never broad-bucket guesses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
