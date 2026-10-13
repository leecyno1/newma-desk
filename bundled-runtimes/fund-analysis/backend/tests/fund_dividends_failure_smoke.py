import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import sync_fund_dividends
from services.tushare_service import TushareDataService


class FundDividendsFailureTests(unittest.TestCase):
    def make_service(self, responses):
        service = TushareDataService.__new__(TushareDataService)
        service.mock_mode = False
        service.strict_no_mock = True

        def fund_div(ts_code):
            response = responses[ts_code]
            if isinstance(response, Exception):
                raise response
            return response

        service._pro = SimpleNamespace(fund_div=fund_div)
        return service

    def run_sync(self, service, codes, repo):
        output = io.StringIO()
        with (
            patch.object(sync_fund_dividends, "init_database"),
            patch.object(sync_fund_dividends, "get_strict_tushare_service", return_value=service),
            patch.object(sync_fund_dividends, "get_fund_dividends_repo", return_value=repo),
            patch.object(sync_fund_dividends, "select_candidates", return_value=codes),
            patch.object(sys, "argv", ["sync_fund_dividends", "--throttle", "0"]),
            redirect_stdout(output),
        ):
            exit_code = sync_fund_dividends.main()
        return exit_code, json.loads(output.getvalue())

    def test_source_failures_propagate(self):
        for error in (TimeoutError("timeout"), RuntimeError("rate limited"), PermissionError("denied")):
            with self.subTest(error=type(error).__name__):
                service = self.make_service({"FAIL.OF": error})
                with self.assertRaises(type(error)):
                    service.get_fund_dividends("FAIL.OF")

    def test_failed_fetch_preserves_existing_events_and_reports_failure(self):
        old_rows = [{"ex_date": "2026-03-11", "div_cash": 0.05}]
        stored = {"FAIL.OF": list(old_rows)}
        repo = Mock()
        repo.replace_fund_dividends.side_effect = lambda code, rows: stored.update({code: rows})
        service = self.make_service({"FAIL.OF": TimeoutError("timeout")})
        exit_code, summary = self.run_sync(service, ["FAIL.OF"], repo)
        self.assertEqual(stored["FAIL.OF"], old_rows)
        repo.replace_fund_dividends.assert_not_called()
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["funds_without_dividends"], 0)

    def test_partial_failure_exits_nonzero_and_continues_other_funds(self):
        service = self.make_service({
            "FAIL.OF": TimeoutError("timeout"),
            "EMPTY.OF": pd.DataFrame(),
            "OK.OF": pd.DataFrame([{"ex_date": "20260311", "div_cash": 0.05}]),
        })
        repo = Mock()
        exit_code, summary = self.run_sync(service, ["FAIL.OF", "EMPTY.OF", "OK.OF"], repo)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["funds_without_dividends"], 1)
        self.assertEqual(summary["funds_with_dividends"], 1)
        self.assertEqual(summary["total_events"], 1)
        self.assertEqual([call.args[0] for call in repo.replace_fund_dividends.call_args_list], ["EMPTY.OF", "OK.OF"])

    def test_write_failure_exits_nonzero(self):
        service = self.make_service({"FAIL.OF": pd.DataFrame(), "OK.OF": pd.DataFrame()})
        repo = Mock()
        repo.replace_fund_dividends.side_effect = [RuntimeError("write failed"), 0]
        exit_code, summary = self.run_sync(service, ["FAIL.OF", "OK.OF"], repo)
        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["funds_without_dividends"], 1)

    def test_successful_empty_result_keeps_replace_semantics(self):
        service = self.make_service({"EMPTY.OF": pd.DataFrame()})
        repo = Mock()
        exit_code, summary = self.run_sync(service, ["EMPTY.OF"], repo)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["funds_without_dividends"], 1)
        repo.replace_fund_dividends.assert_called_once_with("EMPTY.OF", [])

    def test_no_candidates_is_successful_noop(self):
        repo = Mock()
        exit_code, summary = self.run_sync(self.make_service({}), [], repo)
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["requested"], 0)
        repo.replace_fund_dividends.assert_not_called()


if __name__ == "__main__":
    unittest.main()
