import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.alert_scan import AlertScanService


class FakePoolRepo:
    def list_pools(self):
        return [{"id": "pool-1", "name": "核心池"}]

    def list_members(self, pool_id: str, status=None):
        if status == "candidate":
            return [
                {
                    "id": "member-candidate",
                    "pool_id": pool_id,
                    "fund_id": "FUND-SALES-STALE",
                    "fund_wind_code": "519674.OF",
                    "status": "candidate",
                    "next_review_date": "2026-07-01",
                }
            ]
        return [
            {
                "id": f"member-{status}",
                "pool_id": pool_id,
                "fund_id": "FUND-TAIL-001",
                "status": status or "core",
                "next_review_date": "2026-01-01",
            }
        ] if status == "core" else []


class FakeMetricRepo:
    def get_latest_panel(self, target_type, target_id):
        return [
            {"metric_name": "max_drawdown", "metric_value": "-0.03"},
            {"metric_name": "annualized_return", "metric_value": "0.01"},
        ]


class FakePeerService:
    def build_peer_percentiles(self, wind_code: str, window: str = "1y"):
        return {
            "target_id": wind_code,
            "metrics": {
                "professional_score": {"percentile": 18},
                "annualized_return": {"percentile": 15},
            },
        }


class FakeSalesRuleRepo:
    def get_latest_rule(self, member):
        if member["fund_id"] == "FUND-SALES-STALE":
            return {
                "wind_code": "519674.OF",
                "purchase_status": "open",
                "purchase_fee_rate": None,
                "redemption_fee_rules": [],
                "risk_level": "",
                "source_updated_at": "2026-04-01",
            }
        return {
            "wind_code": member.get("fund_wind_code") or member["fund_id"],
            "purchase_status": "open",
            "purchase_fee_rate": 0.001,
            "redemption_fee_rules": [{"min_days": 7, "fee_rate": 0.0}],
            "risk_level": "R3",
            "source_updated_at": "2026-06-01",
        }


class FakeAlertRepo:
    def __init__(self):
        self.created = []

    def create_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": f"event-{len(self.created)}", **kwargs}


def main() -> int:
    repo = FakeAlertRepo()
    service = AlertScanService(
        pool_repo=FakePoolRepo(),
        metric_repo=FakeMetricRepo(),
        alert_repo=repo,
        peer_service=FakePeerService(),
        sales_rule_repo=FakeSalesRuleRepo(),
        today=date(2026, 6, 4),
    )
    summary = service.scan()
    event_types = {event.get("event_type") for event in summary.get("events", [])}
    if "review_due" not in event_types:
        raise AssertionError(f"Expected review_due alert: {summary}")
    if "peer_percentile" not in event_types:
        raise AssertionError(f"Expected peer_percentile alert: {summary}")
    if "sales_rule_evidence" not in event_types:
        raise AssertionError(f"Expected sales_rule_evidence alert: {summary}")
    sales_rule_events = [event for event in summary.get("events", []) if event.get("event_type") == "sales_rule_evidence"]
    if not sales_rule_events or sales_rule_events[0].get("severity") != "high":
        raise AssertionError(f"Expected high severity stale sales-rule evidence alert: {sales_rule_events}")
    sales_rule_message = sales_rule_events[0].get("message", "")
    if "30 天复核窗口" not in sales_rule_message or "R1-R5" not in sales_rule_message:
        raise AssertionError(f"Expected sales-rule alert to mention 30-day window and R1-R5: {sales_rule_message}")

    print("OK alert scan detects review due, weak peer percentile, and stale sales-rule evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
