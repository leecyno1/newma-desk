import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
from repositories.fund_pool_repo import FundPoolRepo
from repositories.metric_snapshot_repo import MetricSnapshotRepo
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


class FakeManagerRepo:
    def get_current_fund_tenure_context(self, fund_code):
        return {}

    def list_fund_manager_departures(self, fund_code, start_date, end_date):
        return []


class FakePeerService:
    def build_peer_percentiles(self, wind_code, window="1y"):
        return {"metrics": {}}


class FakeAlertRepo:
    def __init__(self, open_events=None):
        self.created = []
        self._open_events = open_events or []

    def create_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": f"event-{len(self.created)}", **kwargs}

    def has_open_event(self, fund_id, event_type):
        return any(
            event.get("fund_id") == fund_id and event.get("event_type") == event_type
            and event.get("status") != "resolved"
            for event in self._open_events + self.created
        )


def main() -> int:
    repo = FakeAlertRepo()
    service = AlertScanService(
        pool_repo=FakePoolRepo(),
        metric_repo=FakeMetricRepo(),
        alert_repo=repo,
        manager_repo=FakeManagerRepo(),
        peer_service=FakePeerService(),
    )
    summary = service.scan()
    if summary.get('created', 0) < 1:
        print(f"Expected at least one alert event, got: {summary}")
        return 1
    if not any(event.get('event_type') == 'drawdown' for event in repo.created):
        print(f"Expected drawdown alert event, got: {repo.created}")
        return 1

    # 已有未解决 drawdown 事件时不重复创建，避免每日调度堆积重复事件
    repo = FakeAlertRepo(open_events=[{"fund_id": "FUND-TEST-001", "event_type": "drawdown", "status": "new"}])
    service = AlertScanService(
        pool_repo=FakePoolRepo(),
        metric_repo=FakeMetricRepo(),
        alert_repo=repo,
        manager_repo=FakeManagerRepo(),
        peer_service=FakePeerService(),
    )
    summary = service.scan()
    if any(event.get('event_type') == 'drawdown' for event in repo.created):
        print(f"Expected drawdown dedup against open event, got: {repo.created}")
        return 1
    print('OK alert scan service')
    return 0


class AlertMetricIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
        if not initdb or not pg_ctl:
            raise RuntimeError("initdb and pg_ctl are required for isolated PostgreSQL tests")
        directory = tempfile.TemporaryDirectory(prefix="alert-metric-identity-", dir="/tmp")
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        data = root / "data"
        subprocess.run([initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8"], check=True, capture_output=True)
        subprocess.run([pg_ctl, "-D", str(data), "-l", str(root / "postgres.log"), "-o", f"-h '' -k {root} -F", "-w", "start"], check=True, capture_output=True)
        cls.addClassCleanup(subprocess.run, [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"], check=True, capture_output=True)
        cls.engine = create_engine(URL.create("postgresql+psycopg2", username="postgres", database="postgres", query={"host": str(root)}))
        cls.addClassCleanup(cls.engine.dispose)
        names = ("funds", "fund_pools", "pool_members", "data_source_snapshots", "metric_snapshots")
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
            conn.execute(text("TRUNCATE pool_members, fund_pools, funds, metric_snapshots, data_source_snapshots CASCADE"))
            self.pool_id = conn.execute(text("INSERT INTO fund_pools (name) VALUES ('研究测试池') RETURNING id")).scalar_one()
        self.enterContext(patch.object(database, "init_database", side_effect=AssertionError("production initialization forbidden")))
        self.pool_repo = FundPoolRepo()
        self.pool_repo._engine = self.engine
        self.metric_repo = MetricSnapshotRepo()
        self.metric_repo._engine = self.engine
        self.alert_repo = FakeAlertRepo()
        self.service = AlertScanService(
            pool_repo=self.pool_repo, metric_repo=self.metric_repo, alert_repo=self.alert_repo,
            manager_repo=FakeManagerRepo(), peer_service=FakePeerService(), include_peer_metrics=False,
        )

    def member(self, code="000001.OF", use_uuid=True, status="watch"):
        with self.engine.begin() as conn:
            fund_uuid = conn.execute(text("INSERT INTO funds (wind_code, name) VALUES (:code, :code) RETURNING id"), {"code": code}).scalar_one()
            fund_id = str(fund_uuid) if use_uuid else code
            member_id = conn.execute(text("""
                INSERT INTO pool_members (pool_id, fund_id, status) VALUES (:pool, :fund, :status) RETURNING id
            """), {"pool": self.pool_id, "fund": fund_id, "status": status}).scalar_one()
        return fund_id, member_id

    def metric(self, target_id, value="-0.22", target_type="fund"):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO metric_snapshots (target_type, target_id, as_of_date, metric_name, metric_value, metric_window)
                VALUES (:target_type, :target_id, '2026-09-20', 'max_drawdown', :value, '1y')
            """), {"target_type": target_type, "target_id": target_id, "value": value})

    def test_uuid_member_reads_code_metrics_and_retains_event_relationships(self):
        fund_id, member_id = self.member()
        self.metric("000001.OF")
        member = self.pool_repo.list_members(str(self.pool_id), status="watch")[0]
        self.assertEqual((member["fund_id"], member["fund_wind_code"]), (fund_id, "000001.OF"))
        self.assertEqual(self.metric_repo.get_latest_panel("fund", fund_id), [])
        self.assertEqual(len(self.metric_repo.get_latest_panel("fund", "000001.OF")), 1)
        summary = self.service.scan()
        self.assertEqual(summary["created"], 1)
        event = summary["events"][0]
        self.assertEqual(event["event_type"], "drawdown")
        self.assertEqual(event["severity"], "high")
        self.assertEqual((event["fund_id"], event["pool_member_id"]), (fund_id, member_id))
        self.assertEqual(event["details"], {"current_drawdown": -0.22, "pool_id": self.pool_id})

    def test_code_member_remains_supported(self):
        fund_id, _ = self.member(use_uuid=False)
        self.metric("000001.OF")
        summary = self.service.scan()
        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["events"][0]["fund_id"], fund_id)

    def test_repeat_scan_deduplicates_against_original_uuid(self):
        self.member()
        self.metric("000001.OF")
        self.assertEqual(self.service.scan()["created"], 1)
        self.assertEqual(self.service.scan()["created"], 0)

    def test_existing_open_uuid_event_is_not_recreated(self):
        fund_id, _ = self.member()
        self.metric("000001.OF")
        self.alert_repo._open_events.append({"fund_id": fund_id, "event_type": "drawdown", "status": "new"})
        self.assertEqual(self.service.scan()["created"], 0)

    def test_resolved_uuid_event_allows_new_drawdown_event(self):
        fund_id, _ = self.member()
        self.metric("000001.OF")
        self.alert_repo._open_events.append({"fund_id": fund_id, "event_type": "drawdown", "status": "resolved"})
        self.assertEqual(self.service.scan()["created"], 1)

    def test_missing_or_other_fund_metrics_do_not_trigger_alert(self):
        self.member()
        self.metric("000002.OF")
        self.metric("000001.OF", target_type="manager")
        self.assertEqual(self.service.scan()["created"], 0)

    def test_same_scan_keeps_each_member_bound_to_its_own_metrics(self):
        safe_id, _ = self.member("000001.OF")
        weak_id, _ = self.member("000002.OF", status="core")
        self.metric("000001.OF", "-0.03")
        self.metric("000002.OF", "-0.16")
        summary = self.service.scan()
        self.assertEqual(summary["created"], 1)
        event = summary["events"][0]
        self.assertEqual((event["fund_id"], event["severity"]), (weak_id, "medium"))
        self.assertNotEqual(event["fund_id"], safe_id)

    def test_drawdown_thresholds_remain_unchanged(self):
        expected = {}
        for index, (value, severity, status) in enumerate([
            ("-0.149", None, "watch"), ("-0.15", "medium", "watch"),
            ("-0.199", "medium", "core"), ("-0.20", "high", "candidate"),
        ], start=1):
            code = f"{index:06d}.OF"
            fund_id, _ = self.member(code, status=status)
            self.metric(code, value)
            if severity:
                expected[fund_id] = severity
        summary = self.service.scan()
        self.assertEqual({event["fund_id"]: event["severity"] for event in summary["events"]}, expected)


if __name__ == '__main__':
    if main():
        raise SystemExit(1)
    unittest.main()
