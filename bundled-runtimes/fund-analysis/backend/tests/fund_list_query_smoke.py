import ast
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from repositories.fund_repo import FundRepo


class FundListQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initdb = shutil.which("initdb")
        pg_ctl = shutil.which("pg_ctl")
        if not initdb or not pg_ctl:
            raise RuntimeError("initdb and pg_ctl are required for isolated PostgreSQL tests")
        directory = tempfile.TemporaryDirectory(prefix="fund-list-", dir="/tmp")
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        data = root / "data"
        subprocess.run(
            [initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8"],
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            [pg_ctl, "-D", str(data), "-l", str(root / "postgres.log"), "-o", f"-h '' -k {root} -F", "-w", "start"],
            check=True, capture_output=True, text=True,
        )
        cls.addClassCleanup(
            subprocess.run, [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"],
            check=True, capture_output=True, text=True,
        )
        cls.engine = create_engine(URL.create(
            "postgresql+psycopg2", username="postgres", database="postgres", query={"host": str(root)},
        ))
        cls.addClassCleanup(cls.engine.dispose)
        tree = ast.parse(Path(database.__file__).read_text())
        cls.tables = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for name in ("funds", "holdings", "managers", "fund_sales_rules"):
                    if node.value.startswith(f"CREATE TABLE IF NOT EXISTS {name} ("):
                        cls.tables[name] = node.value
        if len(cls.tables) != 4:
            raise AssertionError("Expected all four fund-list table definitions")

    def setUp(self):
        self.ids = {code: f"00000000-0000-0000-0000-{i:012d}" for i, code in enumerate(("A.OF", "B.OF", "C.OF"), 1)}
        with self.engine.begin() as conn:
            for name in self.tables:
                conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            for statement in self.tables.values():
                conn.execute(text(statement))
            conn.execute(text("ALTER TABLE holdings ADD COLUMN fund_id TEXT"))
            conn.execute(text("ALTER TABLE holdings ALTER COLUMN wind_code DROP NOT NULL"))
            for code, identifier in self.ids.items():
                conn.execute(text("""
                    INSERT INTO funds (id, wind_code, name, type, nav, nav_date, total_asset,
                                       manager_ids, performance_data, risk_metrics, raw_data)
                    VALUES (:id, :code, :code, '股票型', 1, CURRENT_DATE, 10, ARRAY['M1'],
                            '{"annualized_return_1y": 0.1}', '{"max_drawdown_1y": -0.1}',
                            '{"info": {"management_fee": "1", "custodian_fee": "0.2"}}')
                """), {"id": identifier, "code": code})
            conn.execute(text("INSERT INTO managers (wind_code, name, management_years) VALUES ('M1', 'Manager', 5)"))
            rows = [
                ("A.OF", None, "2026Q1", "S1", 1),
                ("A.OF", None, "2026Q1", "S2", 1),
                (None, self.ids["A.OF"], "2026Q1", "S3", 1),
                (None, self.ids["A.OF"], "2026Q1", "S4", 1),
                ("A.OF", self.ids["A.OF"], "2026Q1", "S5", 1),
                ("A.OF", self.ids["B.OF"], "2026Q1", "S6", 1),
                ("A.OF", self.ids["A.OF"], "", "S7", 1),
                ("A.OF", self.ids["A.OF"], "2026Q1", "", 1),
                ("A.OF", self.ids["A.OF"], "2026Q1", "S8", 0),
                ("A.OF", self.ids["A.OF"], "2026Q1", "S9", None),
                ("A.OF", self.ids["A.OF"], "2026Q1", "S10", -1),
            ]
            conn.execute(text("""
                INSERT INTO holdings (wind_code, fund_id, quarter, stock_code, weight)
                VALUES (:code, :fund_id, :quarter, :stock, :weight)
            """), [dict(zip(("code", "fund_id", "quarter", "stock", "weight"), row)) for row in rows])
        self.repo = FundRepo()
        self.repo._engine = self.engine

    def test_summary_does_not_rescan_holdings_per_fund(self):
        plans = []

        def capture_plan(conn, cursor, statement, parameters, context, executemany):
            if "GROUP BY checklist_status" in statement:
                cursor.execute("EXPLAIN (FORMAT JSON) " + statement, parameters)
                plans.append(cursor.fetchone()[0][0]["Plan"])

        event.listen(self.engine, "before_cursor_execute", capture_plan)
        try:
            self.repo.list_funds(page_size=1)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_plan)
        self.assertEqual(len(plans), 1)

        def check(node, correlated=False):
            correlated = correlated or node.get("Subplan Name", "").startswith("SubPlan")
            self.assertFalse(
                correlated and node.get("Relation Name") == "holdings",
                "Fund list summary must not rescan holdings in a per-fund subplan",
            )
            for child in node.get("Plans", []):
                check(child, correlated)

        check(plans[0])

    def test_holdings_count_preserves_or_identity_semantics(self):
        result = self.repo.list_funds(sort_by="wind_code", sort_order="asc")
        counts = {row["wind_code"]: row["holding_count"] for row in result["funds"]}
        self.assertEqual(counts, {"A.OF": 6, "B.OF": 1, "C.OF": 0})
        self.assertEqual(result["total"], 3)

    def test_holdings_filter_and_summary_cover_full_filtered_universe(self):
        with_holdings = self.repo.list_funds(has_holdings=True, page_size=1)
        self.assertEqual(with_holdings["total"], 1)
        self.assertEqual(with_holdings["funds"][0]["wind_code"], "A.OF")
        without_holdings = self.repo.list_funds(has_holdings=False, page_size=1)
        self.assertEqual(without_holdings["total"], 2)
        summary = without_holdings["summary"]["market_research_checklist"]
        self.assertEqual(sum(summary["status_buckets"].values()), 2)
        self.assertEqual(summary["primary_gap_buckets"], {"持仓明细": 2})

    def test_evidence_sort_and_pagination_remain_valid(self):
        result = self.repo.list_funds(sort_by="evidence_coverage", page_size=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["funds"][0]["wind_code"], "A.OF")
        page = self.repo.list_funds(sort_by="wind_code", sort_order="asc", page=2, page_size=1)
        self.assertEqual(page["funds"][0]["wind_code"], "B.OF")
        empty = self.repo.list_funds(keyword="NO_MATCH")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["funds"], [])
        self.assertEqual(empty["summary"]["market_research_checklist"]["status_buckets"], {})

    def test_schema_with_only_wind_code(self):
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE holdings DROP COLUMN fund_id"))
        result = self.repo.list_funds(keyword="A.OF")
        self.assertEqual(result["funds"][0]["holding_count"], 4)

    def test_schema_with_only_fund_id(self):
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE holdings DROP COLUMN wind_code CASCADE"))
        result = self.repo.list_funds(keyword="A.OF")
        self.assertEqual(result["funds"][0]["holding_count"], 3)

    def test_missing_holdings_table(self):
        with self.engine.begin() as conn:
            conn.execute(text("DROP TABLE holdings"))
        result = self.repo.list_funds(has_holdings=False)
        self.assertEqual(result["total"], 3)
        self.assertTrue(all(row["holding_count"] == 0 for row in result["funds"]))


if __name__ == "__main__":
    unittest.main()
