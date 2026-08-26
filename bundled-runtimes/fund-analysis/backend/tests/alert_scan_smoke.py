import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.alert_scan import AlertScanService


class FakePoolRepo:
    def list_pools(self):
        return [{"id": "pool-1", "name": "默认候选池"}]

    def list_members(self, pool_id: str, status=None):
        return [
            {
                "id": "member-1",
                "pool_id": pool_id,
                "fund_id": "FUND-TEST-001",
                "status": status or 'watch',
            }
        ]


class FakeMetricRepo:
    def get_latest_panel(self, target_type, target_id):
        return [
            {"metric_name": "max_drawdown", "metric_value": "-0.22"},
            {"metric_name": "annualized_return", "metric_value": "0.08"},
        ]


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
    )
    summary = service.scan()
    if summary.get('created', 0) < 1:
        print(f"Expected at least one alert event, got: {summary}")
        return 1
    if not any(event.get('event_type') == 'drawdown' for event in repo.created):
        print(f"Expected drawdown alert event, got: {repo.created}")
        return 1
    print('OK alert scan service')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
