"""启动 DDL 被长读事务阻塞时必须在有限时间内放弃，而不是把后端启动无限期卡死。"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
from database import get_database_url, init_database
from sqlalchemy import create_engine, text

BLOCKED_BUDGET_SECONDS = 20
LOCK_TIMEOUT_SECONDS = 5


def main() -> int:
    database._initialized_database_url = None

    blocker_engine = create_engine(get_database_url())
    blocker = blocker_engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(text("SELECT 1 FROM manager_profiles LIMIT 1"))

    outcome = {}

    def run_init():
        try:
            outcome["value"] = init_database()
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    try:
        worker = threading.Thread(target=run_init, daemon=True)
        started = time.monotonic()
        worker.start()
        worker.join(timeout=BLOCKED_BUDGET_SECONDS)
        elapsed = time.monotonic() - started

        if worker.is_alive():
            raise AssertionError(
                f"init_database blocked longer than {BLOCKED_BUDGET_SECONDS}s behind a long read transaction"
            )
        if "error" in outcome:
            raise AssertionError(f"init_database raised instead of degrading: {outcome['error']}")
        if outcome.get("value") is not False:
            raise AssertionError(f"blocked DDL must give up and return False, got {outcome.get('value')}")
        if elapsed > BLOCKED_BUDGET_SECONDS - LOCK_TIMEOUT_SECONDS:
            raise AssertionError(f"init_database must fail fast under lock contention, took {elapsed:.1f}s")
    finally:
        blocker_tx.rollback()
        blocker.close()
        blocker_engine.dispose()

    # 读事务释放后重跑：幂等 DDL 补齐并成功，降级可自愈
    database._initialized_database_url = None
    if init_database() is not True:
        raise AssertionError("init_database must succeed once the blocking read transaction is released")

    print("OK init_database degrades fast behind long read transactions and self-heals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
