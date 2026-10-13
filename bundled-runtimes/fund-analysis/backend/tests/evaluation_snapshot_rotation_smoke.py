import ast
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from repositories.fund_evaluation_snapshot_repo import FundEvaluationSnapshotRepo
from scripts import save_evaluation_snapshots as batch
from services.fund_evaluation_history_service import FundEvaluationHistoryService


class Evaluation:
    def __init__(self):
        self.failed = set()
        self.calls = []

    def load_context(self, code):
        self.calls.append(code)
        if code in self.failed:
            raise RuntimeError("source unavailable")
        return {"found": True, "code": code}

    def evaluate_from_context(self, context, window="1y"):
        return {
            "status": "ok", "methodology_version": "test_v1",
            "target": {"wind_code": context["code"], "as_of_date": "2026-08-01"},
            "peer_context": {"metric_window": window},
            "evaluation": {"overall_score": 70, "dimension_scores": {}, "source_snapshot_ids": []},
        }


class SnapshotRotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
        if not initdb or not pg_ctl:
            raise RuntimeError("initdb and pg_ctl are required for isolated PostgreSQL tests")
        directory = tempfile.TemporaryDirectory(prefix="snapshot-rotation-", dir="/tmp")
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        data = root / "data"
        subprocess.run([initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8"], check=True, capture_output=True)
        subprocess.run([pg_ctl, "-D", str(data), "-l", str(root / "postgres.log"), "-o", f"-h '' -k {root} -F", "-w", "start"], check=True, capture_output=True)
        cls.addClassCleanup(subprocess.run, [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"], check=True, capture_output=True)
        cls.engine = create_engine(URL.create("postgresql+psycopg2", username="postgres", database="postgres", query={"host": str(root)}))
        cls.addClassCleanup(cls.engine.dispose)
        definitions = {}
        for node in ast.walk(ast.parse(Path(database.__file__).read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for name in ("funds", "fund_evaluation_snapshots"):
                    if node.value.startswith(f"CREATE TABLE IF NOT EXISTS {name} ("):
                        definitions[name] = node.value
        with cls.engine.begin() as conn:
            for name in ("funds", "fund_evaluation_snapshots"):
                conn.execute(text(definitions[name]))
            conn.execute(text("CREATE TABLE portfolios (id INTEGER PRIMARY KEY, status TEXT)"))
            conn.execute(text("CREATE TABLE portfolio_holdings (portfolio_id INTEGER, wind_code TEXT)"))
            conn.execute(text("CREATE TABLE metric_snapshots (target_type TEXT, target_id TEXT, as_of_date DATE)"))

    def setUp(self):
        with self.engine.begin() as conn:
            conn.execute(text("TRUNCATE fund_evaluation_snapshots, funds, portfolios, portfolio_holdings, metric_snapshots CASCADE"))
        self.evaluation = Evaluation()
        self.repo = FundEvaluationSnapshotRepo(engine=self.engine)
        self.history = FundEvaluationHistoryService(evaluation_service=self.evaluation, snapshot_repo=self.repo)
        self.enterContext(patch.object(batch, "get_engine", return_value=self.engine))
        self.enterContext(patch.object(batch, "FundEvaluationService", return_value=self.evaluation))
        self.enterContext(patch.object(batch, "FundEvaluationHistoryService", return_value=self.history))

    def fund(self, code, snapshot=True, window="1y"):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO funds (wind_code, name, raw_data) VALUES (:code, :code, '{\"unrelated\": {\"kept\": true}}') ON CONFLICT (wind_code) DO NOTHING"), {"code": code})
            conn.execute(text("INSERT INTO metric_snapshots VALUES ('fund', :code, '2026-08-01')"), {"code": code})
        if snapshot:
            self.history.save_current(code, window=window)
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE fund_evaluation_snapshots SET created_at = '2026-08-02' WHERE wind_code = :code"), {"code": code})
        self.evaluation.calls.clear()

    def run_batch(self, codes=None, window="1y", limit=50):
        args = ["save_evaluation_snapshots", "--window", window, "--limit", str(limit)]
        if codes:
            args += ["--codes", *codes]
        output = io.StringIO()
        with patch.object(sys, "argv", args), redirect_stdout(output):
            result = batch.main()
        return result, json.loads(output.getvalue())

    def snapshot_rows(self):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT * FROM fund_evaluation_snapshots ORDER BY wind_code, id")).fetchall()

    def test_unchanged_batch_rotates_without_mutating_history(self):
        for code in ("A.OF", "B.OF", "C.OF"):
            self.fund(code)
        before = self.snapshot_rows()
        seen = []
        for _ in range(3):
            codes = batch.pick_candidates(1, fresh_quota=0)
            seen += codes
            status, payload = self.run_batch(codes)
            self.assertEqual((status, payload["unchanged_count"]), (0, 1))
        self.assertEqual(seen, ["A.OF", "B.OF", "C.OF"])
        self.assertEqual(self.snapshot_rows(), before)

    def test_automatic_batches_progress_from_fresh_to_unchanged_history(self):
        for code in ("A.OF", "B.OF", "C.OF", "D.OF"):
            self.fund(code)
        for code in ("E.OF", "F.OF"):
            self.fund(code, snapshot=False)
        for expected in (["E.OF", "F.OF"], ["A.OF", "B.OF"], ["C.OF", "D.OF"]):
            self.evaluation.calls.clear()
            status, payload = self.run_batch(limit=2)
            self.assertEqual(status, 0)
            self.assertEqual(payload["candidate_count"], 2)
            self.assertEqual(self.evaluation.calls, expected)

    def test_failed_continuity_candidate_yields_to_next(self):
        self.fund("A.OF")
        self.fund("B.OF")
        self.evaluation.failed.add("A.OF")
        status, payload = self.run_batch(["A.OF"])
        self.assertEqual((status, payload["failed_count"]), (1, 1))
        self.assertEqual(batch.pick_candidates(1, fresh_quota=0), ["B.OF"])

    def test_failed_fresh_candidate_yields_to_next(self):
        self.fund("A.OF", snapshot=False)
        self.fund("B.OF", snapshot=False)
        self.evaluation.failed.add("A.OF")
        self.run_batch(["A.OF"])
        self.assertEqual(batch.pick_candidates(1, fresh_quota=1), ["B.OF"])

    def test_attempts_are_window_scoped(self):
        for code in ("A.OF", "B.OF"):
            self.fund(code)
            self.fund(code, window="3y")
        self.run_batch(["A.OF"], window="1y")
        self.assertEqual(batch.pick_candidates(1, fresh_quota=0, window="1y"), ["B.OF"])
        self.assertEqual(batch.pick_candidates(1, fresh_quota=0, window="3y"), ["A.OF"])

    def test_freshness_means_no_snapshot_in_requested_window(self):
        self.fund("A.OF", window="1y")
        self.assertEqual(batch.pick_candidates(1, fresh_quota=1, window="3y"), ["A.OF"])

    def test_automatic_batch_passes_window_to_selection(self):
        self.fund("A.OF", window="1y")
        status, payload = self.run_batch(window="3y", limit=1)
        self.assertEqual((status, payload["saved_count"]), (0, 1))
        self.assertEqual(len(self.repo.list_history("A.OF", "3y")), 1)

    def test_attempt_metadata_preserves_other_fields_and_windows(self):
        self.fund("A.OF")
        self.run_batch(["A.OF"], window="3y")
        self.run_batch(["A.OF"])
        with self.engine.connect() as conn:
            raw = conn.execute(text("SELECT raw_data FROM funds WHERE wind_code = 'A.OF'")).scalar_one()
        self.assertEqual(raw["unrelated"], {"kept": True})
        self.assertEqual(set(raw.get("evaluation_snapshot_attempts", {})), {"1y", "3y"})

    def test_partial_failure_returns_nonzero_and_processes_other_funds(self):
        self.fund("A.OF")
        self.fund("B.OF")
        self.evaluation.failed.add("A.OF")
        status, payload = self.run_batch(["A.OF", "B.OF"])
        self.assertEqual(status, 1)
        self.assertEqual((payload["failed_count"], payload["unchanged_count"]), (1, 1))
        self.assertEqual(self.evaluation.calls, ["A.OF", "B.OF"])

    def test_empty_batch_is_success(self):
        self.assertEqual(self.run_batch()[0], 0)

    def test_holdings_rotate_inside_priority_pool(self):
        for code in ("A.OF", "B.OF", "C.OF"):
            self.fund(code)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO portfolios VALUES (1, 'active')"))
            conn.execute(text("INSERT INTO portfolio_holdings VALUES (1, 'A.OF'), (1, 'B.OF')"))
        self.run_batch(["A.OF"])
        self.assertEqual(batch.pick_candidates(1, fresh_quota=0), ["B.OF"])

    def test_holdings_do_not_displace_reserved_fresh_slot(self):
        self.fund("A.OF")
        self.fund("B.OF")
        self.fund("C.OF", snapshot=False)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO portfolios VALUES (1, 'draft')"))
            conn.execute(text("INSERT INTO portfolio_holdings VALUES (1, 'A.OF')"))
        self.assertEqual(batch.pick_candidates(2, fresh_quota=1), ["A.OF", "C.OF"])

    def test_unused_quota_fills_from_other_pool(self):
        self.fund("A.OF")
        self.fund("B.OF")
        self.assertEqual(batch.pick_candidates(2, fresh_quota=1), ["A.OF", "B.OF"])

    def test_nonpositive_limit_is_noop(self):
        self.fund("A.OF")
        self.assertEqual(batch.pick_candidates(0), [])
        self.assertEqual(batch.pick_candidates(-1), [])

    def test_only_fresh_pool_fills_unused_continuity_quota(self):
        self.fund("A.OF", snapshot=False)
        self.fund("B.OF", snapshot=False)
        self.assertEqual(batch.pick_candidates(2, fresh_quota=1), ["A.OF", "B.OF"])

    def test_null_raw_data_can_record_attempt_without_changing_fund_dates(self):
        self.fund("A.OF")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE funds SET raw_data = NULL WHERE wind_code = 'A.OF'"))
            before = conn.execute(text("SELECT updated_at, nav_date FROM funds WHERE wind_code = 'A.OF'")).fetchone()
        self.assertEqual(self.run_batch(["A.OF"])[0], 0)
        with self.engine.connect() as conn:
            after = conn.execute(text("SELECT updated_at, nav_date FROM funds WHERE wind_code = 'A.OF'")).fetchone()
            raw = conn.execute(text("SELECT raw_data FROM funds WHERE wind_code = 'A.OF'")).scalar_one()
        self.assertEqual(before, after)
        self.assertEqual(set(raw["evaluation_snapshot_attempts"]), {"1y"})

    def test_holdings_duplicates_and_closed_portfolios_do_not_waste_slots(self):
        for code in ("A.OF", "B.OF", "C.OF"):
            self.fund(code)
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO portfolios VALUES (1, 'active'), (2, 'closed')"))
            conn.execute(text("INSERT INTO portfolio_holdings VALUES (1, 'C.OF'), (1, 'C.OF'), (2, 'B.OF')"))
        self.assertEqual(batch.pick_candidates(2, fresh_quota=0), ["C.OF", "A.OF"])

    def test_new_manual_snapshot_is_not_masked_by_old_attempt(self):
        self.fund("A.OF")
        self.fund("B.OF")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE funds SET raw_data = '{\"evaluation_snapshot_attempts\": {\"1y\": \"2026-07-01T00:00:00Z\"}}' WHERE wind_code = 'A.OF'"))
            conn.execute(text("UPDATE fund_evaluation_snapshots SET created_at = '2026-09-01' WHERE wind_code = 'A.OF'"))
        self.assertEqual(batch.pick_candidates(1, fresh_quota=0), ["B.OF"])

    def test_recording_failure_returns_nonzero_but_does_not_stop_batch(self):
        self.fund("A.OF")
        self.fund("B.OF")
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE FUNCTION reject_attempt() RETURNS trigger AS $$
                BEGIN
                    IF NEW.wind_code = 'A.OF' THEN RAISE EXCEPTION 'attempt write unavailable'; END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))
            conn.execute(text("CREATE TRIGGER reject_attempt BEFORE UPDATE ON funds FOR EACH ROW EXECUTE FUNCTION reject_attempt()"))
        try:
            status, payload = self.run_batch(["A.OF", "B.OF"])
        finally:
            with self.engine.begin() as conn:
                conn.execute(text("DROP TRIGGER reject_attempt ON funds"))
                conn.execute(text("DROP FUNCTION reject_attempt()"))
        self.assertEqual(status, 1)
        self.assertEqual((payload["failed_count"], payload["unchanged_count"]), (1, 2))
        self.assertIn("记录调度尝试失败", payload["failed_sample"]["A.OF"])
        with self.engine.connect() as conn:
            raw = conn.execute(text("SELECT raw_data FROM funds WHERE wind_code = 'B.OF'")).scalar_one()
        self.assertIn("1y", raw["evaluation_snapshot_attempts"])


if __name__ == "__main__":
    unittest.main()
