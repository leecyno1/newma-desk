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


class FakeManagerRepo:
    def get_current_fund_tenure_context(self, fund_code):
        return {}

    def list_fund_manager_departures(self, fund_code, start_date, end_date):
        return []


class FakeAlertRepo:
    def __init__(self):
        self.created = []

    def create_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": f"event-{len(self.created)}", **kwargs}

    def has_open_event(self, fund_id, event_type):
        return False


def main() -> int:
    repo = FakeAlertRepo()
    service = AlertScanService(
        pool_repo=FakePoolRepo(),
        metric_repo=FakeMetricRepo(),
        alert_repo=repo,
        peer_service=FakePeerService(),
        manager_repo=FakeManagerRepo(),
        today=date(2026, 6, 4),
    )
    summary = service.scan()
    event_types = {event.get("event_type") for event in summary.get("events", [])}
    if "review_due" not in event_types:
        raise AssertionError(f"Expected review_due alert: {summary}")
    if "peer_percentile" not in event_types:
        raise AssertionError(f"Expected peer_percentile alert: {summary}")
    if "sales_rule_evidence" in event_types:
        raise AssertionError(f"sales_rule_evidence alerts must not be produced (fund_sales_rules has no data source): {summary}")

    print("OK alert scan detects review due and weak peer percentile without sales-rule zombie alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
