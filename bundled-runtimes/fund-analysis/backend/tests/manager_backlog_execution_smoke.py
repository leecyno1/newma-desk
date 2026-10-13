"""Exercise the upstream backlog entry without network calls or database writes."""
import contextlib
import io
import json
import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import sync_fund_manager_tenure as sync


def run(backlog, results):
    service = Mock()
    service.sync_manager.side_effect = results
    output = io.StringIO()
    with patch.object(sys, "argv", ["sync", "--snapshot-backlog", "3", "--throttle", "0"]), \
         patch.dict(os.environ, {"FUND_DATABASE_INIT_MODE": "check"}), \
         patch.object(sync, "load_shared_database_environment") as config, \
         patch.object(sync, "prepare_database") as prepare, \
         patch.object(sync, "select_snapshot_backlog_managers", return_value=backlog) as select, \
         patch.object(sync, "get_strict_tushare_service") as source, \
         patch.object(sync, "FundManagerTenureSyncService", return_value=service), \
         contextlib.redirect_stdout(output):
        code = sync.main()
        config.assert_called_once()
        prepare.assert_called_once_with("check")
        select.assert_called_once_with(3)
        service.sync_fund.assert_not_called()
        if not backlog:
            source.assert_not_called()
    return code, json.loads(output.getvalue().splitlines()[-1]), service


code, summary, service = run([], [])
assert code == 0 and summary["reason"] == "no_snapshot_backlog"
service.sync_manager.assert_not_called()

managers = [("甲|男|硕士", 4, 1), ("乙|女|硕士", 2, 0)]
code, summary, service = run(managers, [
    {"status": "synced", "current_tenure_count": 4, "nav_points_saved": 120},
    {"status": "failed"},
])
assert code == 1 and summary["requested"] == 2
assert summary["synced"] == 1 and summary["failed"] == 1
assert [call.args[0] for call in service.sync_manager.call_args_list] == [row[0] for row in managers]

code, summary, _ = run(managers[:1], [{"status": "synced"}])
assert code == 0 and summary["synced"] == 1
print("PASS backlog empty/success/partial failure, manager-level dispatch and check-only startup")
