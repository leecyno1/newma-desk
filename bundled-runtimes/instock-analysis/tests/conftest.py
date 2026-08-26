import os
import tempfile


_TEST_CACHE_DIR = tempfile.TemporaryDirectory(prefix="instock-tests-")
os.environ.setdefault(
    "INSTOCK_ANALYSIS_HISTORY_DB_PATH",
    os.path.join(_TEST_CACHE_DIR.name, "analysis_history.sqlite3"),
)
os.environ.setdefault(
    "INSTOCK_SECTOR_FUND_FLOW_DB_PATH",
    os.path.join(_TEST_CACHE_DIR.name, "sector_fund_flow.sqlite3"),
)
os.environ.setdefault(
    "INSTOCK_ROTATION_SHADOW_DB_PATH",
    os.path.join(_TEST_CACHE_DIR.name, "rotation_shadow_state.sqlite3"),
)


# Native analysis imports and SQLite history can be delayed by other local
# research jobs. Keep HTTP fixture tests deterministic on a busy workstation.
os.environ.setdefault("ASYNC_TEST_TIMEOUT", "30")
