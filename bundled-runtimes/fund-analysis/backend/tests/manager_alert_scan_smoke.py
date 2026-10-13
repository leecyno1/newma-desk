import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
from repositories.manager_repo import ManagerRepo
from services.alert_scan import AlertScanService


class FakePoolRepo:
    def __init__(self, members):
        self._members = members

    def list_pools(self):
        return [{"id": "pool-1", "name": "默认候选池"}]

    def list_members(self, pool_id: str, status=None):
        member_status = status or "watch"
        return [m for m in self._members if m.get("status", "watch") == member_status or status is None]


class FakeMetricRepo:
    def get_latest_panel(self, target_type, target_id):
        return []


class FakeAlertRepo:
    def __init__(self, existing=None):
        self.created = []
        self._existing = existing or []

    def create_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": f"event-{len(self.created)}", **kwargs}

    def event_exists(self, fund_id, event_type, detail_key, detail_value):
        for event in self._existing + self.created:
            if event.get("fund_id") != fund_id or event.get("event_type") != event_type:
                continue
            details = event.get("details") or {}
            if str(details.get(detail_key)) == str(detail_value):
                return True
        return False

    def has_open_event(self, fund_id, event_type):
        return False


class FakeManagerRepo:
    def __init__(self, contexts):
        self._contexts = contexts

    def get_current_fund_tenure_context(self, fund_code):
        return self._contexts.get(str(fund_code).strip().upper(), {})

    def list_fund_manager_departures(self, fund_code, start_date, end_date):
        return []


class FakePeerService:
    def build_peer_percentiles(self, fund_id, window="1y"):
        return {"metrics": {}}


def _member(fund_id, status="watch"):
    return {
        "id": f"member-{fund_id}",
        "pool_id": "pool-1",
        "fund_id": fund_id,
        "fund_wind_code": fund_id,
        "status": status,
    }


def _run(members, contexts, existing=None):
    repo = FakeAlertRepo(existing=existing)
    service = AlertScanService(
        pool_repo=FakePoolRepo(members),
        metric_repo=FakeMetricRepo(),
        alert_repo=repo,
        peer_service=FakePeerService(),
        manager_repo=FakeManagerRepo(contexts),
        today=date.today(),
        include_peer_metrics=False,
    )
    summary = service.scan()
    return repo, summary


def main() -> int:
    recent_start = (date.today() - timedelta(days=10)).isoformat()
    old_start = (date.today() - timedelta(days=400)).isoformat()

    # 1. 新任经理（10 天前上任）的 watch 成员 → 产生 manager_change，severity=medium
    repo, summary = _run([_member("FUND-NEW-MGR")], {"FUND-NEW-MGR": {"start_date": recent_start, "manager_ids": ["M1"]}})
    events = [e for e in repo.created if e.get("event_type") == "manager_change"]
    if len(events) != 1:
        print(f"Expected one manager_change event for recent manager, got: {repo.created}")
        return 1
    event = events[0]
    if event.get("severity") != "medium":
        print(f"Watch member manager_change should be medium, got: {event.get('severity')}")
        return 1
    details = event.get("details") or {}
    if details.get("manager_start_date") != recent_start or details.get("wind_code") != "FUND-NEW-MGR":
        print(f"manager_change details incomplete: {details}")
        return 1

    # 2. candidate/core 成员 → severity=high
    repo, _ = _run([_member("FUND-CORE", status="core")], {"FUND-CORE": {"start_date": recent_start, "manager_ids": ["M1"]}})
    events = [e for e in repo.created if e.get("event_type") == "manager_change"]
    if len(events) != 1 or events[0].get("severity") != "high":
        print(f"Core member manager_change should be high, got: {repo.created}")
        return 1

    # 3. 老经理（400 天前上任）→ 不产生事件
    repo, _ = _run([_member("FUND-OLD-MGR")], {"FUND-OLD-MGR": {"start_date": old_start, "manager_ids": ["M1"]}})
    if any(e.get("event_type") == "manager_change" for e in repo.created):
        print(f"Old manager should not trigger manager_change, got: {repo.created}")
        return 1

    # 4. 无现任经理记录 → 不产生事件
    repo, _ = _run([_member("FUND-NO-MGR")], {})
    if any(e.get("event_type") == "manager_change" for e in repo.created):
        print(f"Missing manager record should not trigger manager_change, got: {repo.created}")
        return 1

    # 5. 同一经理变更已有事件（任意状态）→ 不重复创建
    existing = [{
        "fund_id": "FUND-NEW-MGR",
        "event_type": "manager_change",
        "status": "resolved",
        "details": {"manager_start_date": recent_start},
    }]
    repo, summary = _run([_member("FUND-NEW-MGR")], {"FUND-NEW-MGR": {"start_date": recent_start, "manager_ids": ["M1"]}}, existing=existing)
    if any(e.get("event_type") == "manager_change" for e in repo.created):
        print(f"Duplicate manager_change should be suppressed, got: {repo.created}")
        return 1

    print("OK manager alert scan service")
    return 0


class ManagerDepartureTests(unittest.TestCase):
    today = date(2026, 9, 20)

    @classmethod
    def setUpClass(cls):
        initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
        if not initdb or not pg_ctl:
            raise RuntimeError("initdb and pg_ctl are required for isolated PostgreSQL tests")
        directory = tempfile.TemporaryDirectory(prefix="manager-alert-", dir="/tmp")
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        data = root / "data"
        subprocess.run([initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8"], check=True, capture_output=True)
        subprocess.run([pg_ctl, "-D", str(data), "-l", str(root / "postgres.log"), "-o", f"-h '' -k {root} -F", "-w", "start"], check=True, capture_output=True)
        cls.addClassCleanup(subprocess.run, [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"], check=True, capture_output=True)
        cls.engine = create_engine(URL.create("postgresql+psycopg2", username="postgres", database="postgres", query={"host": str(root)}))
        cls.addClassCleanup(cls.engine.dispose)
        names = ("funds", "managers", "manager_fund_tenures")
        definitions = {}
        for node in ast.walk(ast.parse(Path(database.__file__).read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for name in names:
                    if node.value.startswith(f"CREATE TABLE IF NOT EXISTS {name} ("):
                        definitions[name] = node.value
        with cls.engine.begin() as conn:
            for name in names:
                conn.execute(text(definitions[name]))

    def setUp(self):
        with self.engine.begin() as conn:
            conn.execute(text("TRUNCATE manager_fund_tenures, managers, funds CASCADE"))
        self.enterContext(patch.object(database, "init_database", side_effect=AssertionError("production initialization forbidden")))
        self.manager_repo = ManagerRepo()
        self.manager_repo._engine = self.engine
        self.alert_repo = FakeAlertRepo()
        self.tenure("A", current=True)
        self.service = AlertScanService(
            pool_repo=FakePoolRepo([_member("000001.OF")]),
            metric_repo=FakeMetricRepo(), alert_repo=self.alert_repo,
            peer_service=FakePeerService(), manager_repo=self.manager_repo,
            today=self.today, include_peer_metrics=False,
        )

    def tenure(self, manager_id, end_days=None, current=False, start_days=400, code="000001.OF"):
        start = self.today - timedelta(days=start_days)
        end = self.today - timedelta(days=end_days) if end_days is not None else None
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO funds (wind_code, name) VALUES (:code, :code) ON CONFLICT DO NOTHING"), {"code": code})
            conn.execute(text("INSERT INTO managers (wind_code, name) VALUES (:manager, :manager) ON CONFLICT DO NOTHING"), {"manager": manager_id})
            conn.execute(text("""
                INSERT INTO manager_fund_tenures (manager_id, fund_code, start_date, end_date, is_current, source)
                VALUES (:manager, :code, :start, :end, :current, 'tushare.fund_manager')
            """), {"manager": manager_id, "code": code, "start": start, "end": end, "current": current})
        return start, end

    def departures(self, summary):
        return [item for item in summary["events"] if item.get("details", {}).get("change_type") == "departure"]

    def test_pure_departure_preserves_current_team_evaluation_start(self):
        start, end = self.tenure("B", end_days=10)
        before = self.manager_repo.get_current_fund_tenure_context("000001.OF")
        summary = self.service.scan()
        self.assertEqual(summary["created"], 1)
        event = self.departures(summary)[0]
        self.assertEqual(event["event_type"], "manager_change")
        self.assertEqual(event["severity"], "medium")
        self.assertIn("离任", event["title"])
        self.assertIn("离任", event["message"])
        self.assertNotIn("现任经理团队", event["message"])
        details = event["details"]
        self.assertEqual(details["departed_manager_id"], "B")
        self.assertEqual(details["tenure_start_date"], start.isoformat())
        self.assertEqual(details["manager_end_date"], end.isoformat())
        self.assertEqual(details["days_since_manager_end"], 10)
        self.assertEqual(details["source"], "tushare.fund_manager")
        self.assertNotIn("manager_start_date", details)
        self.assertEqual(self.manager_repo.get_current_fund_tenure_context("000001.OF"), before)

    def test_departure_severity_follows_member_status(self):
        self.tenure("B", end_days=2)
        for status, expected in (("watch", "medium"), ("candidate", "high"), ("core", "high")):
            with self.subTest(status=status):
                self.service.alert_repo = FakeAlertRepo()
                self.service.pool_repo = FakePoolRepo([_member("000001.OF", status=status)])
                events = self.departures(self.service.scan())
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["severity"], expected)

    def test_date_window_includes_today_and_thirtieth_day_only(self):
        for manager, days in (("today", 0), ("boundary", 30), ("old", 31), ("future", -1)):
            self.tenure(manager, end_days=days)
        events = self.departures(self.service.scan())
        self.assertEqual({item["details"]["departed_manager_id"] for item in events}, {"today", "boundary"})

    def test_missing_end_current_or_invalid_period_is_not_departure_evidence(self):
        self.tenure("missing")
        self.tenure("still-current", end_days=10, current=True)
        self.tenure("invalid", end_days=10, start_days=5)
        self.assertEqual(self.service.scan()["created"], 0)

    def test_same_day_departures_have_distinct_keys(self):
        self.tenure("B", end_days=10)
        self.tenure("C", end_days=10)
        events = self.departures(self.service.scan())
        self.assertEqual(len(events), 2)
        self.assertEqual(len({event["details"]["manager_departure_key"] for event in events}), 2)

    def test_same_manager_multiple_tenures_are_separate_events(self):
        self.tenure("B", end_days=20)
        self.tenure("B", start_days=15, end_days=5)
        events = self.departures(self.service.scan())
        self.assertEqual(len(events), 2)
        self.assertEqual(len({event["details"]["manager_departure_key"] for event in events}), 2)

    def test_repeat_scan_and_resolved_events_are_not_recreated(self):
        self.tenure("B", end_days=10)
        first = self.service.scan()
        self.assertEqual(first["created"], 1)
        self.assertEqual(self.service.scan()["created"], 0)
        self.service.alert_repo = FakeAlertRepo(existing=[{**event, "status": "resolved"} for event in first["events"]])
        self.assertEqual(self.service.scan()["created"], 0)

    def test_reimported_tenure_does_not_change_departure_identity(self):
        start, end = self.tenure("B", end_days=10)
        self.assertEqual(self.service.scan()["created"], 1)
        self.assertTrue(self.manager_repo.replace_fund_tenures("B", [{
            "fund_code": "000001.OF", "start_date": start, "end_date": end,
            "is_current": False, "source": "tushare.fund_manager",
        }]))
        self.assertEqual(self.service.scan()["created"], 0)

    def test_join_and_departure_on_same_day_both_retain_evidence(self):
        self.tenure("B", end_days=10)
        self.tenure("C", start_days=10, current=True)
        summary = self.service.scan()
        self.assertEqual(summary["created"], 2)
        self.assertEqual(len(self.departures(summary)), 1)
        self.assertEqual(sum("manager_start_date" in event["details"] for event in summary["events"]), 1)
        self.assertEqual(self.service.scan()["created"], 0)

    def test_old_join_event_does_not_suppress_later_departure(self):
        start, _ = self.tenure("B", start_days=20, end_days=10)
        self.alert_repo._existing.append({
            "fund_id": "000001.OF", "event_type": "manager_change", "status": "resolved",
            "details": {"manager_start_date": start.isoformat()},
        })
        self.assertEqual(len(self.departures(self.service.scan())), 1)

    def test_departure_key_cannot_suppress_new_join(self):
        self.tenure("B", start_days=20, end_days=10)
        self.assertEqual(len(self.departures(self.service.scan())), 1)
        self.tenure("C", start_days=20, current=True)
        summary = self.service.scan()
        self.assertEqual(summary["created"], 1)
        self.assertIn("manager_start_date", summary["events"][0]["details"])

    def test_code_lookup_does_not_replace_member_uuid_in_event(self):
        self.tenure("B", end_days=10)
        member = {**_member("f779e1d3-8252-4c55-8a11-f5f275ef91fb"), "fund_wind_code": " 000001.of "}
        self.service.pool_repo = FakePoolRepo([member])
        events = self.departures(self.service.scan())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["fund_id"], member["fund_id"])
        self.assertEqual(events[0]["pool_member_id"], member["id"])
        self.assertEqual(events[0]["details"]["wind_code"], "000001.OF")

    def test_departures_are_scoped_to_the_requested_fund(self):
        self.tenure("B", end_days=10, code="000002.OF")
        self.assertEqual(self.service.scan()["created"], 0)
        self.service.pool_repo = FakePoolRepo([_member("000002.OF")])
        self.assertEqual(len(self.departures(self.service.scan())), 1)

    def test_confirmed_departure_does_not_require_remaining_current_manager(self):
        self.tenure("B", end_days=10, code="000002.OF")
        self.service.pool_repo = FakePoolRepo([_member("000002.OF")])
        self.assertEqual(len(self.departures(self.service.scan())), 1)

    def test_unavailable_database_does_not_fabricate_departures(self):
        self.tenure("B", end_days=10)
        with patch.object(self.engine, "connect", side_effect=RuntimeError("database unavailable")):
            with self.assertLogs("repositories.manager_repo", level="ERROR") as logs:
                summary = self.service.scan()
        self.assertEqual(summary["created"], 0)
        self.assertTrue(any("list_fund_manager_departures" in message for message in logs.output))

    def test_duplicate_members_do_not_repeat_the_same_departure(self):
        self.tenure("B", end_days=10)
        self.service.pool_repo = FakePoolRepo([_member("000001.OF"), {**_member("000001.OF"), "id": "another-member"}])
        self.assertEqual(len(self.departures(self.service.scan())), 1)


if __name__ == "__main__":
    if main():
        raise SystemExit(1)
    unittest.main()
