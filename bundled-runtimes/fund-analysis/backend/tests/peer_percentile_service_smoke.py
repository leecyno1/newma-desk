import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.peer_comparison_service import PeerComparisonService


class InsufficientPeerService(PeerComparisonService):
    def __init__(self):
        super().__init__()
        self.metric_map = {
            f"ACTIVE.{index}": {
                "1y": {
                    "annualized_return": 0.05 + index * 0.01,
                    "max_drawdown": -0.12 + index * 0.01,
                    "annualized_volatility": 0.18,
                    "sharpe_ratio": 0.5 + index * 0.1,
                    "positive_return_ratio": 0.55,
                }
            }
            for index in range(4)
        }

    def _peer_universe(self, wind_code: str):
        peers = [
            {"wind_code": code, "name": code, "type": "股票型"}
            for code in self.metric_map
        ]
        target = next(item for item in peers if item["wind_code"] == wind_code)
        target["classification"] = {
            "status": "classified",
            "evaluation_profile_key": "active_equity",
            "peer_group": "主动权益-测试组",
            "primary_benchmark": "沪深300",
            "minimum_peer_count": 5,
        }
        target["research_profile"] = {}
        return target, peers, "standardized_peer_group_membership"

    def _metric_map(self, wind_codes, fund_rows=None):
        return {code: self.metric_map[code] for code in wind_codes}


def main() -> int:
    result = InsufficientPeerService().build_peer_percentiles("ACTIVE.0", window="1y")
    metrics = result.get("metrics", {})

    if result.get("target_id") != "ACTIVE.0":
        raise AssertionError(f"Unexpected target: {result}")
    if result.get("peer_count", 0) < 1:
        raise AssertionError(f"Expected non-empty peer universe: {result}")
    for metric_name in ["annualized_return", "max_drawdown", "sharpe_ratio"]:
        metric = metrics.get(metric_name)
        if not metric:
            raise AssertionError(f"Missing percentile metric {metric_name}: {result}")
        if metric.get("sample_status") != "insufficient_peer_sample":
            raise AssertionError(f"Explicit small peer group must remain insufficient: {metric}")
        if metric.get("percentile") is not None:
            raise AssertionError(f"Small peer group must not fabricate a percentile: {metric}")

    gap = result.get("peer_metric_gap", {})
    if gap.get("next_action") != "sync_peer_nav_and_rolling_metrics":
        raise AssertionError(f"Small peer group must expose a metric evidence gap: {gap}")
    if result.get("peer_group_source") != "standardized_peer_group_membership":
        raise AssertionError(f"Peer comparison must retain the explicit membership source: {result}")

    print("OK peer percentile service stops ranking when the explicit peer sample is insufficient")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
