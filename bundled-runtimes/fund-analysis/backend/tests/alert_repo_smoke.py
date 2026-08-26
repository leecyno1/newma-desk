import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.alert_repo import AlertRepo


def main() -> int:
    repo = AlertRepo()

    rule = repo.create_rule(
        name="回撤预警-smoke",
        rule_type="drawdown",
        scope_type="pool",
        scope_id="POOL-TEST-001",
        threshold={"max_drawdown": -0.15},
        enabled=True,
        created_by="smoke-test",
    )
    if not rule.get("id"):
        print(f"Expected rule id, got: {rule}")
        return 1

    event = repo.create_event(
        rule_id=rule["id"],
        fund_id="FUND-TEST-001",
        pool_member_id="MEMBER-TEST-001",
        event_type="drawdown",
        severity="high",
        title="回撤超过阈值",
        message="最近回撤超过 -15%",
        status="new",
        details={"current_drawdown": -0.18},
    )
    if event.get("status") != "new":
        print(f"Expected new event, got: {event}")
        return 1

    listed = repo.list_events(status="new")
    if not listed:
        print(f"Expected new events, got: {listed}")
        return 1

    updated = repo.update_event_status(event["id"], status="acknowledged")
    if updated.get("status") != "acknowledged":
        print(f"Expected acknowledged event, got: {updated}")
        return 1

    print("OK alert repository lifecycle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
